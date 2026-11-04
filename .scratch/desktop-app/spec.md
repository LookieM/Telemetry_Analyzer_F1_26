# Plan: Telemetria jako w pełni lokalna aplikacja desktopowa (.exe) + wycofanie Streamlit

## Kontekst
Dziś aplikacja działa w przeglądarce. `run_server.bat` → `python -m telemetria_server` (FastAPI + uvicorn na 127.0.0.1:8765, odbiór UDP z gry, relay do SRT/SimHub) → `webbrowser.open()` → React SPA z `frontend/dist`. Obok żyje stary UI w Streamlit (`gui_app.py`, 1815 linii, i moduły `telemetry/*_ui.py`, ticket `.scratch/review/issues/14`). Część funkcji istnieje tylko tam.

Cel, ustalony z użytkownikiem:
1. **Spakowany `Telemetria.exe`** (PyInstaller): natywne okna Windows (pywebview/WebView2), bez przeglądarki i bez konsoli.
2. **Osobne okno Live** na pionowym monitorze 1080×1920, z zapamiętaną pozycją okien.
3. **Pełne wycofanie Streamlit.** Każda funkcja, której nie ma w React, zostaje przeniesiona („jeżeli czegoś nie ma w nowej apce, spróbuj to zmigrować”). Na końcu usuwamy `gui_app.py`, `*_ui.py`, `telemetry/ui/`, `plots.py` oraz zależności `streamlit` i `plotly`.

Architektura zostaje: backend w Pythonie + React. Zmienia się tylko „opakowanie” i znika drugi UI.

Praca zgodnie z konwencją repo: spec `.scratch/desktop-app/spec.md` + tickety `.scratch/desktop-app/issues/NN-*.md`, każdy ticket kończy się lokalnym commitem (bez push). Testy na kopii `data/` w scratchpadzie.

---

## Faza A: okno desktopowe i .exe (najpierw, małe i od razu użyteczne)

### A1. Ścieżki niezależne od trybu uruchomienia
Nowy `telemetria_server/paths.py`:
- `app_dir()`: dla zamrożonej aplikacji (`sys.frozen`) folder `sys.executable`, w pozostałych przypadkach `REPO_ROOT`. Stamtąd czytany jest `telemetria.toml` i tam domyślnie leży `app_root`.
- `bundle_dir()`: `sys._MEIPASS` po zamrożeniu, w pozostałych przypadkach `REPO_ROOT`. Stamtąd serwowany jest `frontend/dist`.

Zmiany:
- `telemetria_server/config.py`: `REPO_ROOT` → `app_dir()` dla toml i domyślnego `app_root`.
- `telemetria_server/app.py:45`: `dist` → `bundle_dir()/frontend/dist`.
- Fallbacki `Path(__file__).parent.parent` w `telemetry/db.py` (152, 351, 429), `import_session.py` (56, 99) i `wheel_axes_fix.py:93`: sprawdzić, czy serwer zawsze przekazuje `app_root`. Jeśli tak, zostają.

### A2. Launcher desktopowy
Nowy `telemetria_server/desktop.py` i entry `desktop.py` w root (dla PyInstallera). Działanie:
- **Logi:** stdout/stderr → `<app_root>/data/logs/telemetria.log`. W trybie windowed `sys.stdout` to `None`, więc `print` i uvicorn by padły.
- **Serwer:** `load_config()` (ta sama logika co `__main__.py`), potem `uvicorn.Server(uvicorn.Config(create_app(cfg), host, port, log_level="warning"))` w wątku. Okna tworzone dopiero po `server.started`.
- **Pojedyncza instancja:** gdy port HTTP jest zajęty (reuse `_http_port_taken` z `__main__.py`, przenieść do `paths.py` lub wspólnego modułu), pokazać MessageBox „Telemetria już działa” (ctypes `MessageBoxW`) i wyjść.
- **Okna:**
  - główne `http://127.0.0.1:<port>/`;
  - Live `/live` na ekranie portretowym (`webview.screens`, pierwszy z height > width), w pozostałych przypadkach drugie okno obok.
  - Czysta funkcja `pick_live_screen(screens)` pod testy.
- **Stan okien:** pozycja i rozmiar zapisywane do `<app_root>/data/desktop_state.json` (zdarzenia `moved`/`resized`/`closing`) i odtwarzane przy starcie. Zabezpieczenie: jeśli zapisany ekran zniknął, okno wraca na ekran główny.
- **Zamknięcie:** zamknięcie okna głównego zamyka wszystko. `server.should_exit = True`, join wątku, lifespan zatrzymuje `UdpIngest`.
- **localStorage** (`frontend/src/lib/extras.ts`) musi przetrwać restart: `webview.start(private_mode=False, storage_path=<app_root>/data/webview)`.
- `token` z configu doklejany do URL, jak w `__main__.py`.
- Opcja w `telemetria.toml`: `live_window = true|false` (domyślnie true), plus klucz w `telemetria.example.toml`.

Tryb przeglądarkowy (`python -m telemetria_server`, `run_server.bat`) zostaje do developmentu i e2e (`frontend/e2e/global-setup.ts`).

### A3. Build .exe
- `requirements.txt` + `pywebview`; `requirements-dev.txt` + `pyinstaller`.
- `telemetria.spec`:
  - onedir, `console=False`, ikona `desktop/telemetria.ico` (wygenerowana Pillow z favikony SVG z `frontend/index.html`, skrypt `tools/make_icon.py`);
  - `datas`: `frontend/dist`;
  - `hiddenimports`: `collect_submodules("uvicorn")`, `websockets`;
  - `excludes=["streamlit", "plotly"]` (do czasu fazy C, bo `corner_engineer.py:234` ma leniwy import).
- `build_exe.bat`: `npm run build` → `pyinstaller telemetria.spec --distpath desktop_build/dist --workpath desktop_build/work`. Przy pierwszym buildzie kopiuje `telemetria.toml` obok exe i dopisuje `app_root = "<repo>"`, żeby exe używał istniejącej biblioteki `data/`.
- `.gitignore`: `desktop_build/`.

### A4. Testy fazy A
- pytest:
  - `paths.py` (monkeypatch `sys.frozen` / `_MEIPASS`);
  - `pick_live_screen`;
  - zapis i odczyt `desktop_state.json`, w tym brakujący ekran i uszkodzony plik.
- Istniejące `pytest` i `npm test` / `npm run e2e` muszą przejść bez zmian.

---

## Faza B: przeniesienie funkcji ze Streamlit do Reacta

### B0. Audyt parytetu (pierwszy ticket)
Tabela: sekcja Streamlit → miejsce w React albo „brak”, zapisana w `.scratch/desktop-app/parity.md`. Wstępny wynik z przeglądu `gui_app.py` i `frontend/src/pages`:

| Streamlit | React | Status |
|---|---|---|
| Import CSV, statystyki biblioteki, usuwanie sesji | Library | jest |
| Race map, Lap compare, vs Session (ReferencePicker „session”) | Laps tab | jest, sprawdzić corner times cross-session |
| Corners | Corners tab | jest; sprawdzić „Brake markers vs reference” i panel corner engineer |
| Tyres, Strategy, Strategy planner | Tyres / Strategy / Planner | jest |
| Garage, setup duel, generator | Setups | sprawdzić `render_garage()` (tweaker) |
| Session overview: pace chart, fuel/tyre stint chart, tagi, storage | — | **brak** (API tagów istnieje: `api/library.py:76`) |
| Single lap: G-G diagram | — | **brak** |
| ERS / 2026: ślad ERS, ERS per zakręt, tabela ERS, ERS coach, kanały 2026, stint windows | — | **brak** |
| Setup / Stint: follow-up cards, runs, A/B vs wcześniejsza sesja, ewolucja setupu, setup builder + findings + tweaker, tyre & fuel saving | częściowo (Setups) | **brak** w większości |
| Coach: headline diagnozy, top callouts, insights | — | **brak** |
| Track dossier: atlas torów, historia wizyt, ewolucja setupu, overlay sesji, corner dossier vs PB | — | **brak** |

### B1–B7. Porty (każdy to osobny ticket: spec → implementacja → testy → commit)
Wzorzec dla każdego portu:
1. Czystą logikę z `*_ui.py` / `gui_app.py` przenieść do modułu domenowego w `telemetry/` (bez `streamlit`), np. `wear_limit` z `tyres_ui.py`.
2. Endpoint w `telemetria_server/api/<obszar>.py` (pydantic), zarejestrowany w `create_app`.
3. Typy w `frontend/src/api/types.ts` i hook react-query w `frontend/src/api/`.
4. UI z istniejących komponentów (`ui.tsx` Panel/DataTable/Stat, `TraceChart`, `TrackMap`, `StintTimeline`). Wykresy Plotly → uPlot (`TraceChart`) albo proste SVG.
5. Testy: pytest dla endpointu, vitest dla logiki frontu, scenariusz e2e w `frontend/e2e`.

Kolejność (od najtańszych / najczęściej używanych):
- **B1 Przegląd sesji:** pace chart, stint fuel/tyre, edycja tagów, storage. Nowa zakładka „Overview” albo sekcja w Laps.
- **B2 Single lap:** G-G diagram jako panel w Laps tab.
- **B3 Coach:** zakładka „Coach” (`telemetry/diagnosis.py`, `coach.py`, `insights.py`).
- **B4 Energy (ERS / 2026):** zakładka „Energy” (`telemetry/ers.py` + logika z `ers_2026_ui.py`). Zgodna z fazą 5.3 i `ideas/06`, ale port 1:1, bez nowych funkcji z ideas.
- **B5 Setup / Stint:** zakładka „Setup / Stint” (follow-ups, runs, A/B, ewolucja, builder, tweaker, tyre & fuel saving). Logika z `garage_ui.py`, `setup_journal_ui.py`, `stint_coach.py`, `race_windows.py`.
- **B6 Strona toru:** route `/track/:track` (atlas, historia wizyt, ewolucja setupu, overlay, corner dossier vs PB), link z Library i Setups.
- **B7 Resztki z audytu:** brake markers, corner engineer panel, Garage tweaker, jeśli B0 wykaże braki.

Jeśli przy którymś porcie okaże się, że funkcja jest zbędna (zastąpiona przez generator / engineer / duel), decyzję zapisujemy w tickecie i pytam użytkownika, zanim ją pominę.

## Faza C: usunięcie Streamlit
- Usunąć:
  - `gui_app.py`;
  - `telemetry/{ers_2026_ui,garage_ui,setup_journal_ui,strategy_ui,tyres_ui}.py`;
  - `telemetry/ui/`;
  - martwe moduły z ticketu 14 (`lap_views.py`, `session_compare.py`, `plots.py`…), tylko jeśli graf importów z `telemetria_server/` ich nie osiąga;
  - `render_corner_engineer_panel` + `import streamlit` z `corner_engineer.py`.
- `requirements.txt`: usunąć `streamlit` i `plotly`. Z `telemetria.spec` zdjąć `excludes`.
- Zamknąć ticket `review/14`, zaktualizować `.scratch/ROADMAP.md` i pamięć `engineer-tool-roadmap`.
- Sprawdzenie: `grep -r "streamlit\|plotly"` bez trafień poza historią. Pełny pytest, vitest i e2e. Świeży build exe.

---

## Weryfikacja end-to-end
1. `pytest`, `npm run typecheck`, `npm test`, `npm run e2e` po każdej fazie.
2. Faza A, na kopii `data/` w scratchpadzie (`app_root` w toml obok exe):
   - `build_exe.bat`, potem uruchomienie `desktop_build/dist/Telemetria/Telemetria.exe`: dwa okna, Live na pionowym monitorze, brak konsoli;
   - import CSV przez okno dialogowe, schowek (baseline copy), localStorage po restarcie;
   - live: `telemetria_server/replay.py` odtwarza capture z `data/udp_captures` na UDP 20777 → okno Live się aktualizuje, relay do 20778/20779 działa;
   - drugie uruchomienie → komunikat „już działa”;
   - zamknięcie → proces znika, port UDP wolny;
   - log w `data/logs/telemetria.log`.
3. Fazy B i C: każda przeniesiona sekcja porównana na tej samej sesji ze starym Streamlit (uruchomionym przed jego usunięciem) i wpisana do `parity.md`.
4. Na koniec test w grze: sesja treningowa z exe zamiast `run_server.bat`.

## Pliki kluczowe
- Nowe: `telemetria_server/paths.py`, `telemetria_server/desktop.py`, `desktop.py`, `telemetria.spec`, `build_exe.bat`, `tools/make_icon.py`, `.scratch/desktop-app/*`.
- Zmieniane: `telemetria_server/config.py`, `telemetria_server/app.py`, `telemetria_server/__main__.py` (wspólny helper portu), `requirements*.txt`, `.gitignore`, `telemetria.example.toml`, `frontend/src/pages/Session.tsx` (nowe zakładki), `frontend/src/App.tsx` (route toru), `telemetria_server/api/*` (nowe endpointy).
- Usuwane (faza C): `gui_app.py`, `telemetry/*_ui.py`, `telemetry/ui/`, `telemetry/plots.py` i inne martwe moduły.

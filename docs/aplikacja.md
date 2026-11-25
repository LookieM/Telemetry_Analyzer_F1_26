# Telemetria: aplikacja desktopowa

Lokalna aplikacja do analizy telemetrii F1 26. Działa bez przeglądarki i bez internetu: to natywne okno Windows (WebView2), w którym chodzi interfejs React. Obok w tle działa serwer w Pythonie (FastAPI). Serwer odbiera telemetrię UDP z gry, nagrywa sesje do biblioteki i przekazuje pakiety dalej do SRT i SimHub.

## Gdzie co leży

| Co | Ścieżka |
|---|---|
| **Program** | `C:\Users\Lookas\Desktop\Telemetria F1 26\desktop_build\dist\Telemetria\Telemetria.exe` |
| Konfiguracja exe (generowana, nie edytuj) | `desktop_build\dist\Telemetria\telemetria.toml` |
| **Konfiguracja do edycji** | `telemetria.toml` w katalogu głównym repo (opis kluczy: `telemetria.example.toml`) |
| Biblioteka (baza sesji) | `data\telemetry.db` |
| Log aplikacji | `data\logs\telemetria.log` (przy 5 MB rotuje do `telemetria.1.log`) |
| Pozycje okien | `data\desktop_state.json` |
| Pamięć okna (localStorage, np. wybrane kanały) | `data\webview\` |
| Sesje w trakcie nagrywania (checkpointy) | `data\live\` |
| Kopie bazy przed migracjami | `data\backups\` |
| Surowe nagrania UDP | `data\udp_captures\*.f1cap` |

Exe i repo korzystają z **tej samej** biblioteki `data\`. Exe wie, gdzie ona jest, bo `build_exe.bat` wpisuje mu `app_root = "<repo>"`.

Folder `desktop_build\` jest w `.gitignore`. Exe nie trafia do gita i po świeżym klonie trzeba go zbudować (patrz [Budowanie exe](#budowanie-exe)).

## Uruchamianie

**Normalnie:** dwuklik na `Telemetria.exe`. Najwygodniej przypiąć go do paska zadań albo zrobić skrót na pulpicie (PPM na exe → *Wyślij do* → *Pulpit*).

Co się dzieje po starcie:
1. Otwiera się okno główne z napisem „uruchamianie serwera…”, po chwili pokazuje Bibliotekę.
2. Otwiera się drugie okno, **Telemetria — Live**. Przy pierwszym starcie trafia zmaksymalizowane na monitor pionowy (pierwszy ekran wyższy niż szerszy), o ile podłączony jest więcej niż jeden monitor. W przeciwnym razie otwiera się jako okno 540×960.
3. Serwer zaczyna nasłuchiwać UDP na porcie 20777.

Okna zapamiętują pozycję, rozmiar i maksymalizację. Jeśli zapisany monitor zniknie, okno wraca na domyślne miejsce. **Zamknięcie okna głównego zamyka całą aplikację** (także okno Live i serwer). Samo okno Live można zamknąć osobno.

Drugie uruchomienie, gdy aplikacja już działa, kończy się komunikatem „Telemetria już działa (port 8765 jest zajęty)”.

### Opcje wiersza poleceń

Do skrótu albo z terminala, np. `Telemetria.exe --no-live-window`:

| Opcja | Działanie |
|---|---|
| `--no-live-window` | tylko okno główne |
| `--no-record` | nie nasłuchuj UDP (tylko przeglądanie biblioteki) |
| `--udp-port N` | inny port UDP z gry (domyślnie 20777) |
| `--port N` | inny port HTTP serwera (domyślnie 8765) |
| `--app-root ŚCIEŻKA` | inna biblioteka (np. kopia `data\` do testów) |

### Z repo, bez exe (development)

- `.venv\Scripts\python.exe desktop.py` uruchamia tę samą aplikację desktopową z kodu źródłowego. UI bierze z `frontend\dist`, więc wcześniej trzeba zrobić `npm run build` w `frontend\`.
- `run_server.bat` uruchamia sam serwer i otwiera UI w przeglądarce (`http://127.0.0.1:8765/`, Live pod `/live`). Używają go testy e2e.

## Pierwsza konfiguracja

### Gra
W F1 26: *Settings → Telemetry Settings*

- UDP Telemetry: **On**
- UDP Broadcast Mode: **Off**
- UDP IP Address: **127.0.0.1**
- UDP Port: **20777**
- UDP Send Rate: **60 Hz**
- UDP Format: **najnowszy dostępny**

### SRT i SimHub obok
Gra wysyła dane tylko na jeden port. Odbiera je Telemetria i przekazuje każdy pakiet bez zmian dalej. Obecny `telemetria.toml`:

```toml
udp_port = 20777
forward_to = ["127.0.0.1:20778", "127.0.0.1:20779"]   # SRT na 20778, SimHub na 20779
```

W SRT ustaw nasłuch na **20778**, a w SimHub na **20779**. Uwaga: relay działa tylko wtedy, gdy Telemetria jest uruchomiona.

### Pozostałe klucze `telemetria.toml`
Wszystkie są opcjonalne:

| Klucz | Domyślnie | Znaczenie |
|---|---|---|
| `host` | `127.0.0.1` | `0.0.0.0` udostępnia serwer w sieci domowej (wtedy ustaw `access_token`) |
| `port` | `8765` | port HTTP |
| `udp_port` | `20777` | port, na który gra wysyła telemetrię |
| `forward_to` | pusty | lista `host:port` do przekazywania pakietów |
| `access_token` | pusty | hasło do API, podawane raz jako `?token=...` |
| `live_rate_hz` | `10` | ile razy na sekundę odświeża się widok Live |
| `wing_change_s` | `5.0` | dodatkowy czas postoju na wymianę przedniego skrzydła (do decyzji o uszkodzeniach) |
| `live_window` | `true` | czy otwierać osobne okno Live |
| `app_root` | folder repo / exe | gdzie leży biblioteka `data\` |

**Edytuj `telemetria.toml` w repo**, a potem przebuduj exe. Kopia obok exe jest nadpisywana przy każdym buildzie. Jeśli chcesz coś zmienić od razu, bez buildu, możesz tymczasowo poprawić kopię obok exe, ale następny build ją nadpisze.

## Jak używać

Górne menu okna głównego: **Library · Planner · Setups · Live**.

### Skąd biorą się sesje
1. **Automatycznie z gry.** Gdy aplikacja działa w trakcie jazdy, nagrywa sesję. Sesja kończy się, gdy gra zacznie nową sesję, gdy wyśle zdarzenie końca sesji albo po 60 s ciszy. Wtedy trafia do biblioteki sama. Jeśli aplikacja padnie w trakcie jazdy, przy następnym starcie odzyskuje nagranie z `data\live\`.
2. **Import CSV z SRT.** *Library → Import CSV* → wybierz plik, opcjonalnie typ sesji (domyślnie auto), warunki i notatki → *Import*. Po imporcie od razu otwiera się sesja.

### Library
Lista sesji z filtrami (tor, typ sesji, wyszukiwarka po pliku, aucie i notatkach) i statystykami biblioteki. Kliknięcie sesji ją otwiera, a przycisk *Delete* (po potwierdzeniu) usuwa ją z biblioteki. Po wybraniu toru pojawia się skrót do jego strony Setups.

### Sesja (zakładki)
- **Laps:** mapa toru (kolorowanie wybranym kanałem), ślady kierowcy okrążenie vs okrążenie odniesienia (także z innej sesji), delty sektorów i mini-sektorów, tempo sesji, diagram G-G, tabela okrążeń. Pasek nad sesją pozwala ustawić stan toru i warunki.
- **Corners:** gdzie i dlaczego tracisz czas. Czas na każdym zakręcie vs odniesienie, prędkości, punkty hamowania i gazu, balans (podsterowność / nadsterowność) per zakręt i faza, trakcja na wyjściu, blokowanie kół. Kliknięcie zakrętu go przybliża. Przycisk ponownie wykrywa zakręty toru z okrążenia w fokusie.
- **Tyres:** stinty, temperatury i zużycie w trakcie okrążenia, trendy stintów, ciśnienia i okno pracy opon, model mieszanek dla toru (ze wszystkich sesji biblioteki), limit zużycia, przydział mieszanek.
- **Strategy:** strategia wyścigu dla tej sesji.
- **Coach:** odczyt sesji i najważniejsze wskazówki („Top callouts”, kolejne po rozwinięciu).

### Planner
Planer strategii wyścigu dla wybranego toru, oparty na danych z biblioteki.

### Setups
Strona toru:
- **Profil toru:** zakręty wolne / średnie / szybkie, udział pełnego gazu, mocne hamowania.
- **Track baseline:** aktywny setup toru z historią. Przycisk kopiuje wartości do wpisania w garażu, a z historii można przywrócić wcześniejszą wersję.
- **Generated setup:** setup startowy wygenerowany z profilu toru, z oceną pewności każdej wartości.
- **Setups driven here:** setupy, którymi jeździłeś na tym torze. Możesz je nazwać, ustawić jako baseline albo zaznaczyć do pojedynku.
- **Duel:** ranking zaznaczonych setupów. Zwycięzca może zostać baseline.

### Live
Okno na monitor pionowy, w trakcie jazdy:
- **Nagłówek:** tor, typ sesji, okrążenie, pozycja, flagi (SC, PIT, INVALID, kary), pogoda i prognoza deszczu, kropka połączenia (po najechaniu: pakiety/s i straty).
- **Timing:** delta do najlepszego okrążenia sesji i do ostatniego, czas przewidywany, sektory, wykres delty po dystansie.
- **Opony:** mieszanka, wiek, zużycie każdego koła względem limitu.
- **Paliwo:** zużycie na okrążenie, na ile okrążeń wystarczy, zapas.
- **ERS:** tryb, stan baterii, energia oddana i odzyskana.
- **Uszkodzenia**, **rywale** i pasek zdarzeń na dole.

Karty zależą od sesji:
- **wyścig:** strategia + rywale;
- **trening:** inżynier / pojedynek setupów na żywo;
- **kwalifikacje:** żadna z nich.

Program, który już działa (inżynier albo pojedynek), zostaje zawsze widoczny.

Bez gry okno pokazuje „Waiting for the game (UDP)…”. Do testu bez gry można odtworzyć nagranie:

```
.venv\Scripts\python.exe -m telemetria_server.replay data\udp_captures\<plik>.f1cap
```

## Budowanie exe

Exe **nie aktualizuje się sam** po zmianach w kodzie. Po każdej zmianie w kodzie (Python albo frontend) lub w `telemetria.toml` uruchom w katalogu repo:

```
build_exe.bat
```

Skrypt robi trzy kroki: `npm run build` w `frontend\`, potem PyInstaller (`telemetria.spec`), potem kopiuje config obok exe. Wynik trafia do `desktop_build\dist\Telemetria\`.

Przed buildem zamknij działającą aplikację, bo Windows nie pozwoli nadpisać otwartego exe.

Wymagania: `.venv` z `requirements-dev.txt` (zawiera PyInstaller i pywebview) oraz Node/npm z zainstalowanym `frontend\node_modules`. WebView2 jest w Windows 11 domyślnie.

## Problemy

| Objaw | Co zrobić |
|---|---|
| „Telemetria już działa” | Aplikacja jest już otwarta (może zminimalizowana) albo inny program zajął port 8765. Zamknij ją lub ustaw inny `port`. |
| „Serwer nie wystartował” | Szczegóły są w `data\logs\telemetria.log`. |
| Live stoi na „Waiting for the game” | Sprawdź ustawienia UDP w grze (IP 127.0.0.1, port 20777). Sprawdź, czy SRT albo SimHub nie zajmują 20777: mają słuchać na 20778 / 20779. |
| Komunikat o zajętym porcie UDP | Inny program słucha na 20777. Przestaw go na inny port i dodaj ten port do `forward_to`. |
| Okno Live na złym monitorze lub poza ekranem | Zamknij aplikację, usuń `data\desktop_state.json` i uruchom ją ponownie: okna wrócą na domyślne miejsca. |
| SRT / SimHub nic nie dostają | Telemetria musi działać, bo to ona przekazuje pakiety. Sprawdź `forward_to` i porty w tych programach. |
| W exe brakuje nowej funkcji | Exe jest starszy niż kod. Uruchom `build_exe.bat`. |

## Stary interfejs (Streamlit)

`gui_app.py` (Streamlit) jeszcze istnieje i ma kilka funkcji, których nie przeniesiono do aplikacji: Energy/ERS, Setup/Stint + Garage, strona toru, drobne sprawdzenia. Plan migracji i usunięcia Streamlit: `.scratch/desktop-app/` (tickety 06–10, audyt w `parity.md`). Ten interfejs nie jest częścią exe.

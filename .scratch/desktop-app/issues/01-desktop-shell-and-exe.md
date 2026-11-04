# 01: Desktop window + Telemetria.exe (phase A)

**Status:** done
**Area:** packaging · desktop

Spec: `../spec.md` phase A (A1 paths, A2 launcher with main + Live window, A3 PyInstaller build, A4 tests).

## Comments
- 2026-11-04: done. `telemetry/app_paths.py` (app / bundle dir), `telemetria_server/desktop.py` (uvicorn thread + pywebview main and Live windows, positions in `data/desktop_state.json`, log in `data/logs/telemetria.log`, single instance by HTTP port), `desktop.py`, `telemetria.spec`, `build_exe.bat` → `desktop_build/dist/Telemetria/Telemetria.exe` (164 MB onedir, starts in ~1 s). The exe's `telemetria.toml` is generated from the repo's on every build, with `app_root` pinned to the repo library.
- Verified on a sandbox copy of the library: from source (both windows, Live maximized on the portrait screen, live replay over WebSocket, clean shutdown records the session and frees the UDP port, second start refused) and the exe (API, SPA, heavy endpoints). Found and fixed: `telemetry/map_data.py` imported Plotly through `plots._map_xy` (500 on the map in the exe).
- Still to check by the driver: the exe with the game (Live window update, relay to SRT / SimHub).

"""Desktop app: the server runs in a background thread, the UI in native windows (WebView2). No browser, no console.

`python -m telemetria_server.desktop` from a checkout, or `Telemetria.exe` (PyInstaller, entry `desktop.py`).
The main window shows the app; a second window shows the Live view, on the portrait screen when there is one.
Window positions are kept in `<app_root>/data/desktop_state.json`.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Protocol

from .config import Config, http_port_taken, load_config

LOG_MAX_BYTES = 5_000_000
MAIN_DEFAULT = (1600, 1000)
LIVE_DEFAULT = (540, 960)
MIN_VISIBLE = (120, 60)  # a saved window must show at least this much on some screen to be reused
OFFSCREEN = -30000  # Windows parks minimized windows at about (-32000, -32000)

log = logging.getLogger("telemetria.desktop")


class ScreenLike(Protocol):
    x: int
    y: int
    width: int
    height: int


@dataclass
class Geometry:
    x: int | None = None
    y: int | None = None
    width: int = MAIN_DEFAULT[0]
    height: int = MAIN_DEFAULT[1]
    maximized: bool = False

    @classmethod
    def from_dict(cls, raw: Any) -> Geometry | None:
        if not isinstance(raw, dict):
            return None
        try:
            return cls(
                x=None if raw.get("x") is None else int(raw["x"]),
                y=None if raw.get("y") is None else int(raw["y"]),
                width=int(raw["width"]),
                height=int(raw["height"]),
                maximized=bool(raw.get("maximized", False)),
            )
        except (KeyError, TypeError, ValueError):
            return None


# ---------------------------------------------------------------- pure helpers (tested)


def pick_live_screen(screens: Iterable[ScreenLike]) -> ScreenLike | None:
    """The first portrait screen (taller than wide), else None."""
    for s in screens:
        if s.height > s.width:
            return s
    return None


def visible_on(geom: Geometry, screens: Iterable[ScreenLike]) -> bool:
    """True if enough of the window lies on one of the screens (a screen may have been unplugged since)."""
    if geom.x is None or geom.y is None:
        return True  # no position: the OS places it
    for s in screens:
        overlap_w = min(geom.x + geom.width, s.x + s.width) - max(geom.x, s.x)
        overlap_h = min(geom.y + geom.height, s.y + s.height) - max(geom.y, s.y)
        if overlap_w >= MIN_VISIBLE[0] and overlap_h >= MIN_VISIBLE[1]:
            return True
    return False


def default_geometry(kind: str, screens: list[ScreenLike]) -> Geometry:
    if kind == "live":
        portrait = pick_live_screen(screens)
        if portrait is not None and len(screens) > 1:
            return Geometry(x=portrait.x, y=portrait.y, width=portrait.width, height=portrait.height, maximized=True)
        return Geometry(width=LIVE_DEFAULT[0], height=LIVE_DEFAULT[1])
    return Geometry(width=MAIN_DEFAULT[0], height=MAIN_DEFAULT[1])


def initial_geometry(kind: str, state: dict[str, Any], screens: list[ScreenLike]) -> Geometry:
    saved = Geometry.from_dict(state.get(kind))
    if saved is not None and saved.width >= MIN_VISIBLE[0] and saved.height >= MIN_VISIBLE[1] and visible_on(saved, screens):
        return saved
    return default_geometry(kind, screens)


def load_state(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return raw if isinstance(raw, dict) else {}


def save_state(path: Path, state: dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        log.warning("could not save window positions to %s", path, exc_info=True)


class GeometryTracker:
    """Follows a window's moved / resized / maximized / restored events; minimized and maximized
    positions are not kept as the 'normal' geometry."""

    def __init__(self, start: Geometry) -> None:
        self.geom = Geometry(**asdict(start))
        self.minimized = False

    def moved(self, x: int, y: int) -> None:
        if self.minimized or self.geom.maximized or x <= OFFSCREEN or y <= OFFSCREEN:
            return
        self.geom.x, self.geom.y = int(x), int(y)

    def resized(self, width: int, height: int) -> None:
        if self.minimized or self.geom.maximized or width < MIN_VISIBLE[0] or height < MIN_VISIBLE[1]:
            return
        self.geom.width, self.geom.height = int(width), int(height)

    def on_maximized(self) -> None:
        self.minimized = False
        self.geom.maximized = True

    def on_minimized(self) -> None:
        self.minimized = True

    def on_restored(self) -> None:
        if self.minimized:
            self.minimized = False  # back from the taskbar: still maximized or not, as before
            return
        self.geom.maximized = False


# ---------------------------------------------------------------- runtime


def _setup_logging(app_root: Path) -> Path:
    """Windowed exe has no console (sys.stdout is None): send stdout / stderr / logging to a file."""
    log_dir = app_root / "data" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "telemetria.log"
    try:
        if log_path.exists() and log_path.stat().st_size > LOG_MAX_BYTES:
            log_path.replace(log_dir / "telemetria.1.log")
    except OSError:
        pass
    stream = open(log_path, "a", encoding="utf-8", buffering=1)  # noqa: SIM115 - lives as long as the process
    sys.stdout = stream
    sys.stderr = stream
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(name)s %(levelname)s %(message)s", stream=stream, force=True)
    logging.getLogger("telemetria").setLevel(logging.INFO)
    print(f"\n---- Telemetria desktop start {time.strftime('%Y-%m-%d %H:%M:%S')} ----")
    return log_path


def _message_box(text: str, title: str = "Telemetria") -> None:
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, text, title, 0x40)  # MB_ICONINFORMATION
    except Exception:  # noqa: BLE001 - not on Windows: the log has it
        print(f"{title}: {text}")


def _base_url(cfg: Config) -> tuple[str, str]:
    shown = "127.0.0.1" if cfg.host in ("0.0.0.0", "::") else cfg.host
    base = f"http://{shown}:{cfg.port}"
    query = f"?token={cfg.access_token}" if cfg.access_token else ""
    return base, query


PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
html,body{{height:100%;margin:0;background:#0d0f12;color:#e8eaed;font:15px/1.5 'Segoe UI',sans-serif}}
body{{display:flex;align-items:center;justify-content:center;text-align:center}}
b{{color:#e03c31}} code{{color:#9aa0a6}}</style></head><body><div>{body}</div></body></html>"""


def _config(argv: list[str] | None) -> Config:
    parser = argparse.ArgumentParser(prog="Telemetria")
    parser.add_argument("--app-root", type=Path, help="library folder (overrides telemetria.toml)")
    parser.add_argument("--port", type=int, help="HTTP port (default 8765)")
    parser.add_argument("--udp-port", type=int, help="port the game sends telemetry to (default 20777)")
    parser.add_argument("--no-record", action="store_true", help="do not listen for UDP at all")
    parser.add_argument("--no-live-window", action="store_true", help="only the main window")
    args, _ = parser.parse_known_args(argv)
    cfg = load_config()
    if args.app_root:
        cfg.app_root = args.app_root.resolve()
    if args.port:
        cfg.port = args.port
    if args.udp_port is not None:
        cfg.udp_port = args.udp_port
    if args.no_record:
        cfg.record = False
    if args.no_live_window:
        cfg.live_window = False
    return cfg


def main(argv: list[str] | None = None) -> int:
    cfg = _config(argv)
    log_path = _setup_logging(cfg.app_root)
    base, query = _base_url(cfg)

    if http_port_taken(cfg.host, cfg.port):
        print(f"port {cfg.port} taken: another Telemetria is running")
        _message_box(
            f"Telemetria już działa (port {cfg.port} jest zajęty).\n\n"
            "Zamknij poprzednie okno albo ustaw inny 'port' w telemetria.toml."
        )
        return 1

    import uvicorn
    import webview

    from .app import create_app

    server = uvicorn.Server(uvicorn.Config(create_app(cfg), host=cfg.host, port=cfg.port, log_level="warning"))
    server_thread = threading.Thread(target=server.run, name="uvicorn", daemon=True)
    server_thread.start()

    screens = list(webview.screens)
    state_path = cfg.app_root / "data" / "desktop_state.json"
    state = load_state(state_path)
    trackers: dict[str, GeometryTracker] = {}
    windows: dict[str, Any] = {}

    def make_window(kind: str, title: str, **kwargs: Any) -> Any:
        geom = initial_geometry(kind, state, screens)
        window = webview.create_window(
            title,
            width=geom.width,
            height=geom.height,
            x=geom.x,
            y=geom.y,
            maximized=geom.maximized,
            min_size=(360, 300),
            background_color="#0d0f12",
            text_select=True,
            **kwargs,
        )
        tracker = GeometryTracker(geom)
        window.events.moved += tracker.moved
        window.events.resized += tracker.resized
        window.events.maximized += tracker.on_maximized
        window.events.minimized += tracker.on_minimized
        window.events.restored += tracker.on_restored
        trackers[kind] = tracker
        windows[kind] = window
        return window

    def remember() -> None:
        state.update({kind: asdict(t.geom) for kind, t in trackers.items()})
        save_state(state_path, state)

    loading = PAGE.format(body="<b>Telemetria</b><br>uruchamianie serwera…")
    main_window = make_window("main", "Telemetria", html=loading)

    def on_main_closed() -> None:
        remember()
        live = windows.get("live")
        if live is not None:
            try:
                live.destroy()
            except Exception:  # noqa: BLE001 - already gone
                pass

    main_window.events.closed += on_main_closed

    def after_start() -> None:
        while not server.started and server_thread.is_alive():
            time.sleep(0.05)
        if not server.started:
            main_window.load_html(
                PAGE.format(body=f"<b>Serwer nie wystartował.</b><br>Szczegóły w logu:<br><code>{log_path}</code>")
            )
            return
        main_window.load_url(f"{base}/{query}")
        if cfg.live_window:
            live = make_window("live", "Telemetria — Live", url=f"{base}/live{query}")
            live.events.closed += remember

    webview.start(
        after_start,
        private_mode=False,  # keep localStorage (lap extras) between runs
        storage_path=str(cfg.app_root / "data" / "webview"),
    )

    server.should_exit = True
    server_thread.join(timeout=15)
    print("---- Telemetria desktop stop ----")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Server configuration: defaults, overridden by an optional `telemetria.toml` in the app folder
(the repo root, or the folder of Telemetria.exe)."""

from __future__ import annotations

import socket
import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path

from telemetry.app_paths import REPO_ROOT, app_dir  # noqa: F401  (REPO_ROOT re-exported)


@dataclass
class Config:
    host: str = "127.0.0.1"
    port: int = 8765
    udp_port: int = 20777
    record: bool = True  # listen on udp_port and record sessions into the library
    forward_to: str = ""  # "host:port, host:port" (TOML string or list) to relay raw UDP to other apps; empty = off
    access_token: str = ""  # empty = open; otherwise required for /api and /ws
    live_rate_hz: int = 10
    wing_change_s: float = 5.0  # extra stop time for a new front wing (assumed; used by the live damage call)
    app_root: Path = field(default_factory=app_dir)
    live_window: bool = True  # desktop app: open the Live view in its own window (portrait screen if there is one)


def load_config(path: Path | None = None) -> Config:
    """Read `telemetria.toml` (missing file = defaults); unknown keys are ignored."""
    cfg_path = path or app_dir() / "telemetria.toml"
    cfg = Config()
    if not cfg_path.exists():
        return cfg
    with cfg_path.open("rb") as f:
        raw = tomllib.load(f)
    for fld in fields(Config):
        if fld.name in raw:
            value = raw[fld.name]
            if fld.name == "forward_to" and isinstance(value, list):
                value = ", ".join(str(v) for v in value)  # TOML list of "host:port"
            kind = Path if fld.name == "app_root" else type(getattr(cfg, fld.name))
            value = kind(value)
            if fld.name == "app_root" and not value.is_absolute():
                value = (cfg_path.parent / value).resolve()  # relative to the toml, not to the working folder
            setattr(cfg, fld.name, value)
    return cfg


def http_port_taken(host: str, port: int) -> bool:
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind((host, port))
    except OSError:
        return True
    finally:
        probe.close()
    return False

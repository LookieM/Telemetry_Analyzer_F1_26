"""Server configuration: defaults, overridden by an optional `telemetria.toml` at the repo root."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Config:
    host: str = "127.0.0.1"
    port: int = 8765
    udp_port: int = 20777
    record: bool = True  # listen on udp_port and record sessions into the library
    forward_to: str = ""  # "host:port" to relay raw UDP packets (e.g. to SRT); empty = off
    access_token: str = ""  # empty = open; otherwise required for /api and /ws
    live_rate_hz: int = 10
    app_root: Path = field(default_factory=lambda: REPO_ROOT)


def load_config(path: Path | None = None) -> Config:
    """Read `telemetria.toml` (missing file = defaults); unknown keys are ignored."""
    cfg_path = path or REPO_ROOT / "telemetria.toml"
    cfg = Config()
    if not cfg_path.exists():
        return cfg
    with cfg_path.open("rb") as f:
        raw = tomllib.load(f)
    for fld in fields(Config):
        if fld.name in raw:
            kind = Path if fld.name == "app_root" else type(getattr(cfg, fld.name))
            setattr(cfg, fld.name, kind(raw[fld.name]))
    return cfg

"""Where the app lives, for both a source checkout and the frozen Telemetria.exe (PyInstaller onedir).

- `app_dir()`: the folder the user sees. Holds `telemetria.toml` and, by default, the library (`data/`).
  Source checkout: the repo root. Frozen: the folder of `Telemetria.exe`.
- `bundle_dir()`: read-only files shipped with the app (`frontend/dist`).
  Source checkout: the repo root. Frozen: PyInstaller's `_internal` folder (`sys._MEIPASS`).
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_dir() -> Path:
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return REPO_ROOT


def bundle_dir() -> Path:
    meipass = getattr(sys, "_MEIPASS", None)
    if is_frozen() and meipass:
        return Path(meipass)
    return REPO_ROOT

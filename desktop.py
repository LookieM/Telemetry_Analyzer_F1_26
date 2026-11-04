"""Entry point of Telemetria.exe (PyInstaller). From a checkout: `python desktop.py` or `python -m telemetria_server.desktop`."""

import sys

from telemetria_server.desktop import main

if __name__ == "__main__":
    sys.exit(main())

"""`python -m telemetria_server [--host] [--port] [--no-browser]`."""

from __future__ import annotations

import argparse
import threading
import webbrowser

import uvicorn

from .app import create_app
from .config import load_config


def main() -> None:
    parser = argparse.ArgumentParser(prog="telemetria_server")
    parser.add_argument("--host")
    parser.add_argument("--port", type=int)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    cfg = load_config()
    if args.host:
        cfg.host = args.host
    if args.port:
        cfg.port = args.port

    if not args.no_browser:
        shown = "127.0.0.1" if cfg.host in ("0.0.0.0", "::") else cfg.host
        url = f"http://{shown}:{cfg.port}/"
        if cfg.access_token:
            url += f"?token={cfg.access_token}"
        threading.Timer(1.0, webbrowser.open, args=(url,)).start()
    uvicorn.run(create_app(cfg), host=cfg.host, port=cfg.port)


if __name__ == "__main__":
    main()

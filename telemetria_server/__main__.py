"""`python -m telemetria_server [--host] [--port] [--udp-port] [--forward HOST:PORT ...] [--no-record] [--no-browser]`."""

from __future__ import annotations

import argparse
import logging
import socket
import sys
import threading
import webbrowser
from pathlib import Path

import uvicorn

from .app import create_app
from .config import load_config


def _http_port_taken(host: str, port: int) -> bool:
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind((host, port))
    except OSError:
        return True
    finally:
        probe.close()
    return False


def main() -> None:
    parser = argparse.ArgumentParser(prog="telemetria_server")
    parser.add_argument("--host")
    parser.add_argument("--port", type=int, help="HTTP port (default 8765)")
    parser.add_argument("--app-root", type=Path, help="library folder (overrides telemetria.toml)")
    parser.add_argument("--udp-port", type=int, help="port the game sends telemetry to (default 20777)")
    parser.add_argument(
        "--forward",
        action="append",
        metavar="HOST:PORT",
        help="relay every UDP packet to this app; repeat or comma-separate (overrides forward_to in telemetria.toml)",
    )
    parser.add_argument("--no-record", action="store_true", help="do not listen for UDP at all")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    cfg = load_config()
    if args.host:
        cfg.host = args.host
    if args.port:
        cfg.port = args.port
    if args.app_root:
        cfg.app_root = args.app_root.resolve()
    if args.udp_port is not None:
        cfg.udp_port = args.udp_port
    if args.forward is not None:
        cfg.forward_to = ", ".join(args.forward)
    if args.no_record:
        cfg.record = False

    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    logging.getLogger("telemetria").setLevel(logging.INFO)

    shown = "127.0.0.1" if cfg.host in ("0.0.0.0", "::") else cfg.host
    url = f"http://{shown}:{cfg.port}/"
    if cfg.access_token:
        url += f"?token={cfg.access_token}"

    if _http_port_taken(cfg.host, cfg.port):
        print(f"\nThe server already seems to be running at {url} (port {cfg.port} is taken).")
        print("Close the other server window first, or start this one with --port <another port>.\n")
        if not args.no_browser:
            webbrowser.open(url)
        sys.exit(1)

    print(f"Telemetria: {url}   live view: {url.rstrip('/')}/live")
    if not args.no_browser:
        threading.Timer(1.0, webbrowser.open, args=(url,)).start()
    uvicorn.run(create_app(cfg), host=cfg.host, port=cfg.port, log_level="warning")


if __name__ == "__main__":
    main()

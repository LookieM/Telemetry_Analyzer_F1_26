"""Static frontend serving: deep links fall back to index.html, API / files keep their 404s."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from conftest import ROOT
from telemetria_server.app import create_app
from telemetria_server.config import Config


def _dist(tmp_path: Path) -> Path:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>SPA</html>", encoding="utf8")
    (dist / "assets" / "app.js").write_text("console.log(1)", encoding="utf8")
    return dist


def test_spa_fallback(tmp_path):
    with TestClient(create_app(Config(app_root=tmp_path), frontend_dist=_dist(tmp_path))) as c:
        assert c.get("/").text == "<html>SPA</html>"
        for deep in ("/session/25/tyres", "/planner", "/session/3"):
            r = c.get(deep)
            assert r.status_code == 200 and r.text == "<html>SPA</html>"
        asset = c.get("/assets/app.js")
        assert asset.text == "console.log(1)"
        assert "javascript" in asset.headers["content-type"]  # module scripts are refused as text/plain
        assert c.get("/assets/missing.js").status_code == 404
        assert c.get("/api/nope").status_code == 404
        assert c.get("/ws/nope").status_code == 404
        assert c.get("/api/health").json() == {"status": "ok"}


def test_app_root_flag(tmp_path):
    out = subprocess.run(
        [sys.executable, "-m", "telemetria_server", "--help"], cwd=ROOT, capture_output=True, text=True, timeout=60
    )
    assert "--app-root" in out.stdout

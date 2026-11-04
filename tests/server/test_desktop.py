"""Desktop app helpers: app / bundle paths (source vs frozen exe), config next to the exe, window placement."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

from telemetry import app_paths
from telemetria_server import config as config_mod
from telemetria_server.desktop import (
    Geometry,
    GeometryTracker,
    default_geometry,
    initial_geometry,
    load_state,
    pick_live_screen,
    save_state,
    visible_on,
)

LANDSCAPE = SimpleNamespace(x=0, y=0, width=2560, height=1440)
PORTRAIT = SimpleNamespace(x=2560, y=0, width=1080, height=1920)


def test_paths_in_a_checkout_are_the_repo_root(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert app_paths.app_dir() == app_paths.REPO_ROOT
    assert app_paths.bundle_dir() == app_paths.REPO_ROOT


def test_paths_when_frozen(monkeypatch, tmp_path):
    exe = tmp_path / "Telemetria" / "Telemetria.exe"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe))
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "Telemetria" / "_internal"), raising=False)
    assert app_paths.app_dir() == exe.parent.resolve()
    assert app_paths.bundle_dir() == tmp_path / "Telemetria" / "_internal"


def test_frozen_config_reads_the_toml_next_to_the_exe(monkeypatch, tmp_path):
    exe_dir = tmp_path / "Telemetria"
    exe_dir.mkdir()
    (exe_dir / "telemetria.toml").write_text('port = 8799\napp_root = "../library"\nlive_window = false\n', encoding="utf-8")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe_dir / "Telemetria.exe"))
    cfg = config_mod.load_config()
    assert cfg.port == 8799
    assert cfg.live_window is False
    assert cfg.app_root == (tmp_path / "library").resolve()  # relative to the toml


def test_frozen_default_library_is_the_exe_folder(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "Telemetria.exe"))
    assert config_mod.load_config().app_root == tmp_path.resolve()


def test_live_window_goes_to_the_portrait_screen():
    assert pick_live_screen([LANDSCAPE, PORTRAIT]) is PORTRAIT
    assert pick_live_screen([LANDSCAPE]) is None
    geom = default_geometry("live", [LANDSCAPE, PORTRAIT])
    assert (geom.x, geom.y, geom.maximized) == (2560, 0, True)


def test_live_window_without_a_portrait_screen_is_a_plain_window():
    geom = default_geometry("live", [LANDSCAPE])
    assert geom.x is None and not geom.maximized


def test_saved_position_is_reused_while_its_screen_exists():
    state = {"live": {"x": 2600, "y": 100, "width": 900, "height": 1600, "maximized": False}}
    assert initial_geometry("live", state, [LANDSCAPE, PORTRAIT]) == Geometry(2600, 100, 900, 1600, False)
    # portrait monitor unplugged: back to the default instead of an invisible window
    assert initial_geometry("live", state, [LANDSCAPE]) == default_geometry("live", [LANDSCAPE])


def test_garbage_state_falls_back_to_defaults(tmp_path):
    bad = tmp_path / "desktop_state.json"
    bad.write_text("{not json", encoding="utf-8")
    assert load_state(bad) == {}
    assert load_state(tmp_path / "missing.json") == {}
    assert initial_geometry("main", {"main": {"x": "a"}}, [LANDSCAPE]) == default_geometry("main", [LANDSCAPE])
    assert initial_geometry("main", {"main": [1, 2]}, [LANDSCAPE]) == default_geometry("main", [LANDSCAPE])


def test_state_round_trip(tmp_path):
    path = tmp_path / "data" / "desktop_state.json"
    save_state(path, {"main": {"x": 10, "y": 20, "width": 1200, "height": 800, "maximized": True}})
    assert load_state(path)["main"]["maximized"] is True


def test_visible_on_needs_a_real_overlap():
    assert visible_on(Geometry(x=None, y=None), [LANDSCAPE])
    assert not visible_on(Geometry(x=2550, y=0, width=1000, height=800), [LANDSCAPE])  # 10 px on screen
    assert visible_on(Geometry(x=2400, y=0, width=1000, height=800), [LANDSCAPE])


def test_tracker_keeps_the_normal_geometry_through_maximize_and_minimize():
    t = GeometryTracker(Geometry(x=100, y=100, width=1200, height=800))
    t.moved(150, 120)
    t.resized(1300, 850)
    t.on_maximized()
    t.moved(-8, -8)
    t.resized(2576, 1416)
    assert (t.geom.x, t.geom.y, t.geom.width, t.geom.height, t.geom.maximized) == (150, 120, 1300, 850, True)
    t.on_minimized()
    t.moved(-32000, -32000)
    t.on_restored()  # from the taskbar: still maximized
    assert t.geom.maximized and t.geom.x == 150
    t.on_restored()  # un-maximize
    assert not t.geom.maximized

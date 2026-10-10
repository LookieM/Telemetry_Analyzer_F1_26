"""F1 26 track catalog, 50% race distance, tyre allocation sources and game tyre priors."""

from __future__ import annotations

import math

import pytest

from telemetry.compounds import get_allocation, get_game_tyres, save_game_tyres, set_allocation
from telemetry.corners import normalize_track_name
from telemetry.db import init_db
from telemetry.strategy import manual_specs
from telemetry.track_catalog import PIRELLI_2026, RACE_LAPS_FULL, TRACK_LENGTHS_M, catalog_track_names, race_laps
from telemetria_server.udp.srt_columns import TRACKS

F1_26_IDS = [0, 2, 3, 4, 5, 6, 7, 9, 10, 11, 12, 13, 14, 15, 16, 17, 19, 20, 26, 27, 29, 30, 31, 32, 39, 40, 41, 42]

# Spa as the game reported it (TyreSets of a real capture): C4/C3/C2, deltas vs the fitted soft
SPA_SETS = [
    {"actual": 17, "visual": 16, "life": 9, "delta_ms": 0},
    {"actual": 18, "visual": 17, "life": 12, "delta_ms": 550},
    {"actual": 19, "visual": 18, "life": 18, "delta_ms": 1076},
    {"actual": 7, "visual": 7, "life": 22, "delta_ms": 5837},
    {"actual": 8, "visual": 8, "life": 16, "delta_ms": 7535},
]


def test_every_f1_26_track_is_in_the_catalog_with_a_50_percent_distance():
    names = set(catalog_track_names())
    assert len(names) == 28 and {"Madring", "Silverstone Reverse", "Spielberg Reverse", "Zandvoort Reverse"} <= names
    for tid in F1_26_IDS:
        canon = normalize_track_name(TRACKS[tid])
        assert canon in names, (tid, TRACKS[tid])
        assert TRACK_LENGTHS_M[canon] > 3000 and race_laps(canon) == math.ceil(RACE_LAPS_FULL[canon] / 2)
    assert (race_laps("Bahrain"), race_laps("Spielberg"), race_laps("Monza"), race_laps("Madring")) == (29, 36, 27, 29)


@pytest.fixture()
def root(tmp_path):
    init_db(tmp_path)
    return tmp_path


def test_allocation_priority_manual_over_game_over_pirelli(root):
    a = get_allocation("Miami", root)
    assert a.source == "pirelli-2026" and a.roles == dict(zip(PIRELLI_2026["Miami"], ("S", "M", "H")))
    assert get_allocation("Spa", root).source == "none"  # no 2026 nomination found, nothing seen yet

    saved = save_game_tyres("Spa", SPA_SETS, total_laps=11, session_type="Race", app_root=root)
    assert {c: v["role"] for c, v in saved.items() if v["role"] in "SMH"} == {17: "S", 18: "M", 19: "H"}
    spa = get_allocation("Spa", root)
    assert spa.source == "game" and spa.roles == {17: "S", 18: "M", 19: "H"}

    set_allocation("Spa", 16, 17, 18, root)
    assert get_allocation("Spa", root).source == "manual"


def test_manual_specs_use_game_pace_and_life_only_at_the_same_race_length(root):
    save_game_tyres("Spa", SPA_SETS, total_laps=22, session_type="Race", app_root=root)
    alloc, game = get_allocation("Spa", root), get_game_tyres("Spa", root)
    specs = {s.code: s for s in manual_specs(alloc, game, laps=22, wear_limit=70.0)}
    assert specs[17].offset_s == pytest.approx(-0.550) and specs[18].offset_s == 0 and specs[19].offset_s == pytest.approx(0.526)
    assert specs[17].max_laps(70.0, 22) == 9 and specs[19].max_laps(70.0, 22) == 18
    # captured in an 11-lap race: the life numbers do not transfer to a 22-lap race
    save_game_tyres("Spa", SPA_SETS, total_laps=11, session_type="Race", app_root=root)
    specs = {s.code: s for s in manual_specs(alloc, get_game_tyres("Spa", root), laps=22, wear_limit=70.0)}
    assert "life" not in specs[17].source and specs[17].offset_s == pytest.approx(-0.550)


def test_tracks_endpoint_lists_the_whole_catalog(root):
    from fastapi.testclient import TestClient

    from telemetria_server.app import create_app
    from telemetria_server.config import Config

    with TestClient(create_app(Config(record=False, app_root=root), frontend_dist=root / "none")) as c:
        data = c.get("/api/tracks").json()
    assert data["race_share"] == 0.5 and len(data["tracks"]) == 28
    madring = next(t for t in data["tracks"] if t["track"] == "Madring")
    assert madring["race_laps"] == 29 and madring["allocation"]["source"] == "pirelli-2026"
    assert madring["allocation"]["soft"] == "C4"

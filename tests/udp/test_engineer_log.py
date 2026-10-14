from telemetria_server.live.engineer import Engineer, EngineerLap
from telemetry import engineer_log


def _finished(settled_value=31.0):
    e = Engineer(seed=3)
    e.start("short", {"wing_setup_0": 25.0, "wing_setup_1": 20.0}, "Miami", "FP1", False, 1000.0)
    e.stop()
    r = e.result()
    r["settled"] = {"wing_setup_0": settled_value}
    return r


def test_save_and_settled_round_trip(tmp_root):
    assert engineer_log.settled_for("Miami", tmp_root) == {}
    tid = engineer_log.save_test(_finished(), tmp_root)
    assert engineer_log.settled_for("Miami", tmp_root) == {"wing_setup_0": 31.0}
    assert engineer_log.settled_for("Spa", tmp_root) == {}
    engineer_log.save_test(_finished(33.0), tmp_root)           # upsert, not duplicate
    assert engineer_log.settled_for("Miami", tmp_root) == {"wing_setup_0": 33.0}
    tests = engineer_log.list_tests("Miami", tmp_root)
    assert len(tests) == 2 and tests[1]["id"] == tid and tests[0]["result"]["program"] == "short"


def test_next_program_starts_from_the_settled_values(tmp_root):
    engineer_log.save_test(_finished(), tmp_root)
    e = Engineer(seed=1)
    e.start("short", {"wing_setup_0": 25.0, "wing_setup_1": 20.0}, "Miami", "FP1", False, 0.0,
            settled=engineer_log.settled_for("Miami", tmp_root))
    v = e.view()
    assert v["param"]["label"] == "Rear wing" and v["settled"]["wing_setup_0"]["value"] == 31
    e.on_lap(EngineerLap(lap=1, lap_time_s=90.0, setup={"wing_setup_1": 20.0}))
    assert e.result()["baseline"]["wing_setup_0"] == 31.0

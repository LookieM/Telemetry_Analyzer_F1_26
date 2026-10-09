"""Settings round-trips and the import endpoint, all on a temporary library."""

from __future__ import annotations

from pathlib import Path


def test_allocation_roundtrip(client):
    url = "/api/tracks/Bahrain/allocation"
    first = client.get(url).json()
    assert {"track", "source", "soft", "medium", "hard", "roles", "compounds"} <= set(first)
    put = client.put(url, json={"soft": 18, "medium": 19, "hard": 20}).json()
    assert (put["soft"], put["medium"], put["hard"], put["source"]) == (18, 19, 20, "manual")
    assert client.get(url).json()["roles"] == {"18": "S", "19": "M", "20": "H"}
    assert client.get(url).json()["compounds"]["18"]["role"] == "S"
    cleared = client.delete(url).json()
    assert cleared["source"] != "manual"
    assert client.put(url, json={"soft": "x"}).status_code == 422


def test_targets_roundtrip(client):
    url = "/api/compounds/19/targets"
    default = client.get(url).json()
    assert default["compound"] == 19 and default["source"] == "default"
    body = {"temp_lo": 91.5, "temp_hi": 108.0, "hot_front_psi": 24.1, "hot_rear_psi": 22.4}
    saved = client.put(url, json=body).json()
    assert saved["source"] == "saved" and saved["temp_lo"] == 91.5 and saved["hot_rear_psi"] == 22.4
    assert client.get(url).json() == saved
    assert client.put(url, json={"temp_lo": 1}).status_code == 422


def test_strategy_overrides_roundtrip(client):
    url = "/api/tracks/Bahrain/strategy-overrides"
    assert client.get(url).json()["saved"] is False
    base = client.post("/api/strategy/optimise", json={"track": "Bahrain"}).json()
    code = base["specs"][0]["code"]
    put = client.put(url, json={"state": "dry", "params": {"pit_loss_s": 25.0}, "specs": [{"code": code, "deg_s_per_lap": 0.5}]}).json()
    assert put["saved"] and put["params"]["pit_loss_s"] == 25.0
    assert put["compounds"][str(code)]["deg_s_per_lap"] == 0.5
    assert client.get(url).json() == put
    after = client.post("/api/strategy/optimise", json={"track": "Bahrain"}).json()
    assert after["saved_overrides"] and after["params"]["pit_loss_s"] == 25.0
    assert after["specs"][0]["deg_s_per_lap"] == 0.5
    cleared = client.delete(url).json()
    assert cleared["saved"] is False and cleared["params"] == {}


def test_import_errors(client, tmp_path: Path):
    assert client.post("/api/import", json={"path": str(tmp_path / "missing.csv")}).status_code == 404
    assert client.post("/api/import", json={}).status_code == 422
    junk = tmp_path / "junk.csv"
    junk.write_text("a,b\n1,2\n")
    assert client.post("/api/import", json={"path": str(junk)}).status_code in (400, 422)
    assert junk.exists()
    r = client.post("/api/import", files={"file": ("junk.csv", b"a,b\n1,2\n", "text/csv")})
    assert r.status_code in (400, 422)
    assert not list((client.app.state.config.app_root / "data").glob("*.upload.csv"))
    assert client.post("/api/import", data={"x": "1"}, files={"other": ("a.csv", b"x")}).status_code == 422


def _small_csv(lib_root: Path, race_id: int, dest: Path) -> Path:
    from telemetry import db

    full = db.load_session_telemetry(race_id, lib_root)
    full[full["lap"].between(2, 5)].to_csv(dest, sep="\t", index=False)
    return dest


def test_import_upload_and_path(client, lib_root: Path, race_id: int, tmp_path: Path):
    csv = _small_csv(lib_root, race_id, tmp_path / "small.csv")
    r = client.post(
        "/api/import",
        files={"file": ("uploaded_small.csv", csv.read_bytes(), "text/csv")},
        data={"session_type": "Practice", "notes": "from test"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["source_name"] == "uploaded_small.csv" and body["already_existed"] is False
    assert body["lap_count"] >= 3 and body["source_deleted"] is True
    detail = client.get(f"/api/sessions/{body['session_id']}").json()["session"]
    assert detail["source_name"] == "uploaded_small.csv" and detail["session_type"] == "Practice"
    assert not list((lib_root / "data").glob("*.upload.csv"))

    again = client.post("/api/import", files={"file": ("uploaded_small.csv", csv.read_bytes(), "text/csv")}).json()
    assert again["already_existed"] is True and again["session_id"] == body["session_id"]

    other = _small_csv(lib_root, race_id, tmp_path / "other.csv")
    other.write_text(other.read_text().rstrip("\n").rsplit("\n", 1)[0] + "\n")  # different bytes, same data
    by_path = client.post("/api/import", json={"path": str(other)})
    assert by_path.status_code == 200 and other.exists()  # delete_source defaults to false

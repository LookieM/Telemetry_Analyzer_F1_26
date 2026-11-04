"""Coach endpoint: session read + ranked callouts over the whole session."""

from __future__ import annotations


def test_coach_feed_shape(client, race_id):
    r = client.get(f"/api/sessions/{race_id}/coach")
    assert r.status_code == 200
    body = r.json()
    assert body["session_id"] == race_id
    assert isinstance(body["headline"], str) and body["headline"]
    assert body["diagnosis"]["primary_issue"] in {"understeer", "oversteer", "mixed", "balanced"}
    items = body["top"] + body["rest"]
    assert len(body["top"]) <= 8
    for it in items:
        assert it["action_kind"] in {"drive", "setup", "manage", "observe"}
        assert it["severity"] in {"info", "tip", "warning"}
        assert it["title"]
    scores = [it["score"] for it in body["top"]]
    assert scores == sorted(scores, reverse=True)
    assert len({it["id"] for it in items}) == len(items)  # deduplicated


def test_coach_404(client):
    assert client.get("/api/sessions/999999/coach").status_code == 404

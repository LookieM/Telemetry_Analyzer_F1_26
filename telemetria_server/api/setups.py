"""Setups per track: the distinct setups driven in the library, naming, and the offline duel."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from telemetry import duel_store
from telemetry.corners import normalize_track_name

from .. import duel_library
from ..serialization import to_jsonable
from ._common import root_of

router = APIRouter()

MAX_NAME = 60


class DuelBody(BaseModel):
    fingerprints: list[str] = Field(min_length=2, max_length=3)


class NameBody(BaseModel):
    track: str
    name: str = Field(max_length=MAX_NAME)


def _track(track: str) -> str:
    return normalize_track_name(track) or track


@router.get("/tracks/{track}/setups")
def track_setups(track: str, request: Request) -> Any:
    return to_jsonable(duel_library.setups_payload(_track(track), root_of(request)))


@router.post("/tracks/{track}/duel")
def track_duel(track: str, body: DuelBody, request: Request) -> Any:
    fps = body.fingerprints
    if len(set(fps)) != len(fps):
        raise HTTPException(422, "Pick different setups")
    try:
        return to_jsonable(duel_library.run_duel(_track(track), fps, root_of(request)))
    except KeyError as exc:
        raise HTTPException(404, f"Setup {exc.args[0]} was not driven on {_track(track)}") from exc


@router.put("/setups/{fingerprint}/name")
def name_setup(fingerprint: str, body: NameBody, request: Request) -> Any:
    name = duel_store.set_name(fingerprint, _track(body.track), body.name, root_of(request))
    return {"fingerprint": fingerprint, "track": _track(body.track), "name": name}

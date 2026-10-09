"""POST /api/import: a multipart CSV upload, or a JSON body naming a local file."""

from __future__ import annotations

import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, ValidationError

from telemetry.import_session import ImportResult, import_csv

from ..serialization import to_jsonable
from ._common import root_of

router = APIRouter()

CHUNK = 1 << 20


class PathImport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    delete_source: bool = False
    source_name: str | None = None
    session_type: str = ""
    conditions: str = ""
    notes: str = ""


def _run(path: Path, root: Path, **kw: Any) -> ImportResult:
    try:
        return import_csv(path, app_root=root, **kw)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except (ValueError, KeyError) as exc:
        raise HTTPException(400, f"Could not import: {exc}") from exc


@router.post("/import")
async def import_session(request: Request) -> Any:
    root = root_of(request)
    ctype = request.headers.get("content-type", "")
    if ctype.startswith("multipart/form-data"):
        form = await request.form()
        upload = form.get("file")
        if upload is None or not hasattr(upload, "read"):
            raise HTTPException(422, "Multipart field 'file' is required")
        data_dir = root / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=data_dir, suffix=".upload.csv", delete=False) as tmp:
            tmp_path = Path(tmp.name)
            while chunk := await upload.read(CHUNK):
                tmp.write(chunk)
        try:
            result = await run_in_threadpool(
                _run,
                tmp_path,
                root,
                delete_source=True,
                source_name=Path(upload.filename or "upload.csv").name,
                session_type=str(form.get("session_type") or ""),
                conditions=str(form.get("conditions") or ""),
                notes=str(form.get("notes") or ""),
            )
        finally:
            tmp_path.unlink(missing_ok=True)
        return to_jsonable(result)

    try:
        body = PathImport.model_validate(await request.json())
    except (ValidationError, ValueError) as exc:
        raise HTTPException(422, f"Send multipart 'file' or JSON {{path}}: {exc}") from exc
    result = await run_in_threadpool(
        _run,
        Path(body.path),
        root,
        delete_source=body.delete_source,
        source_name=body.source_name,
        session_type=body.session_type,
        conditions=body.conditions,
        notes=body.notes,
    )
    return to_jsonable(asdict(result))

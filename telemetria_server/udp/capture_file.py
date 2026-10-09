"""Raw UDP capture file: magic + records [u32 length][f64 epoch][payload]."""

from __future__ import annotations

import struct
from pathlib import Path
from typing import BinaryIO, Iterator

MAGIC = b"F1CAP\x01"
_REC = struct.Struct("<Id")


class CaptureWriter:
    """Append-only writer; flushes every ``flush_every`` packets."""

    def __init__(self, path: str | Path, flush_every: int = 120) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.flush_every = max(1, flush_every)
        self.count = 0
        self._fh: BinaryIO | None = open(self.path, "wb")
        self._fh.write(MAGIC)

    def write(self, t: float, payload: bytes) -> None:
        if self._fh is None:
            raise ValueError("CaptureWriter is closed")
        self._fh.write(_REC.pack(len(payload), t))
        self._fh.write(payload)
        self.count += 1
        if self.count % self.flush_every == 0:
            self._fh.flush()

    def close(self) -> None:
        if self._fh is not None:
            try:
                self._fh.flush()
            finally:
                self._fh.close()
                self._fh = None

    def __enter__(self) -> "CaptureWriter":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def iter_capture(path: str | Path) -> Iterator[tuple[float, bytes]]:
    """Yield (receive_time, payload); stops quietly at a truncated record."""
    with open(path, "rb") as fh:
        if fh.read(len(MAGIC)) != MAGIC:
            raise ValueError(f"{path}: not an F1CAP v1 capture file")
        while True:
            head = fh.read(_REC.size)
            if len(head) < _REC.size:
                return
            length, t = _REC.unpack(head)
            payload = fh.read(length)
            if len(payload) < length:
                return
            yield t, payload

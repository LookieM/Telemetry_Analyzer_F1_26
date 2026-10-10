"""Decode raw UDP datagrams into numpy records using the generated dtypes in ``structs``."""

from __future__ import annotations

import numpy as np

from .structs import HEADER_DT, PACKET_DT

PACKET_FORMAT = 2026
HEADER_SIZE = HEADER_DT.itemsize  # 29


def parse_packet(data: bytes) -> tuple[int, np.void] | None:
    """Return ``(packet_id, record)`` or None for an unknown id / wrong size / unsupported format.

    ``record['header']`` holds the header fields, ``record['body']`` the payload.
    """
    if len(data) < HEADER_SIZE:
        return None
    if int.from_bytes(data[0:2], "little") != PACKET_FORMAT:
        return None
    pid = data[6]
    dt = PACKET_DT.get(pid)
    if dt is None or len(data) != dt.itemsize:
        return None
    return pid, np.frombuffer(data, dtype=dt, count=1)[0]

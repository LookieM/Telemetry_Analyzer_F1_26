"""F1 UDP packet header (F1 23-F1 25 layout; tolerant of newer formats)."""

from __future__ import annotations

import struct
from dataclasses import dataclass

HEADER_STRUCT = struct.Struct("<HBBBBBQfIIBB")
HEADER_SIZE = HEADER_STRUCT.size  # 29

PACKET_NAMES: dict[int, str] = {
    0: "Motion",
    1: "Session",
    2: "LapData",
    3: "Event",
    4: "Participants",
    5: "CarSetups",
    6: "CarTelemetry",
    7: "CarStatus",
    8: "FinalClassification",
    9: "LobbyInfo",
    10: "CarDamage",
    11: "SessionHistory",
    12: "TyreSets",
    13: "MotionEx",
    14: "TimeTrial",
    15: "LapPositions",
}


@dataclass(frozen=True)
class PacketHeader:
    packet_format: int
    game_year: int
    game_major_version: int
    game_minor_version: int
    packet_version: int
    packet_id: int
    session_uid: int
    session_time: float
    frame_identifier: int
    overall_frame_identifier: int
    player_car_index: int
    secondary_player_car_index: int

    @property
    def packet_name(self) -> str:
        return PACKET_NAMES.get(self.packet_id, f"Unknown({self.packet_id})")


def parse_header(data: bytes) -> PacketHeader | None:
    """Parse the common header; return None if the datagram is too short."""
    if len(data) < HEADER_SIZE:
        return None
    try:
        return PacketHeader(*HEADER_STRUCT.unpack_from(data, 0))
    except struct.error:
        return None


def peek_format_and_id(data: bytes) -> tuple[int, int] | None:
    """Read only packetFormat (offset 0) and packetId (offset 6)."""
    if len(data) < 7:
        return None
    return int.from_bytes(data[0:2], "little"), data[6]

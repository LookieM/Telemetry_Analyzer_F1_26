from pathlib import Path

import numpy as np
import pytest

from telemetria_server.udp.capture_file import iter_capture
from telemetria_server.udp.parse import parse_packet
from telemetria_server.udp.structs import PACKET_DT

EXPECTED = {0: 1325, 1: 926, 2: 1399, 3: 45, 4: 1470, 5: 1233, 6: 1448, 7: 1445, 8: 1134, 9: 1062,
            10: 1133, 11: 1460, 12: 231, 13: 273, 14: 104, 15: 1231, 16: 269}


def test_struct_sizes_match_validated_values():
    assert {k: v.itemsize for k, v in PACKET_DT.items()} == EXPECTED


def test_synthetic_roundtrip_and_rejects():
    buf = bytearray(EXPECTED[6])
    buf[0:2] = (2026).to_bytes(2, "little")
    buf[6] = 6
    pid, rec = parse_packet(bytes(buf))
    assert pid == 6 and rec["header"]["m_packetFormat"] == 2026
    assert parse_packet(bytes(buf[:-1])) is None
    buf[0:2] = (2025).to_bytes(2, "little")
    assert parse_packet(bytes(buf)) is None


CAP = Path(__file__).resolve().parents[2] / "data" / "udp_captures" / "20261009-222554.f1cap"


@pytest.mark.skipif(not CAP.exists(), reason="no local capture")
def test_real_capture_every_packet_parses():
    seen = set()
    for i, (_t, data) in enumerate(iter_capture(CAP)):
        if i > 3000:
            break
        out = parse_packet(data)
        assert out is not None
        seen.add(out[0])
        if out[0] == 6:
            tel = out[1]["body"]["m_carTelemetryData"]
            assert np.all(tel["m_speed"] < 500)
    assert {0, 1, 2, 6, 7} <= seen

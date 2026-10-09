"""Summarize a raw .f1cap capture: python -m telemetria_server.capture_info FILE"""

from __future__ import annotations

import argparse
from pathlib import Path

from .udp.capture_file import iter_capture
from .udp.header import PACKET_NAMES, parse_header


def summarize(path: str | Path) -> dict:
    """Return counts, sizes and frame gaps per packet id plus header info."""
    total = 0
    t_first = t_last = None
    versions: set[tuple] = set()
    uids: set[int] = set()
    per_id: dict[int, dict] = {}
    for t, data in iter_capture(path):
        total += 1
        t_first = t if t_first is None else t_first
        t_last = t
        if len(data) < 7:
            continue
        pid = data[6]
        rec = per_id.setdefault(
            pid, {"name": PACKET_NAMES.get(pid, f"Unknown({pid})"), "count": 0,
                  "sizes": set(), "gaps": 0, "_last": None})
        rec["count"] += 1
        rec["sizes"].add(len(data))
        hdr = parse_header(data)
        if hdr is None:
            continue
        versions.add((hdr.packet_format, hdr.game_year, hdr.game_major_version,
                      hdr.game_minor_version, hdr.packet_version))
        uids.add(hdr.session_uid)
        f = hdr.frame_identifier
        if rec["_last"] is not None and f - rec["_last"] > 1:
            rec["gaps"] += f - rec["_last"] - 1
        if rec["_last"] is None or f > rec["_last"]:
            rec["_last"] = f
    for rec in per_id.values():
        rec.pop("_last")
        rec["sizes"] = sorted(rec["sizes"])
    return {
        "packets": total,
        "duration": (t_last - t_first) if t_first is not None else 0.0,
        "versions": sorted(versions),
        "session_uids": sorted(uids),
        "by_id": dict(sorted(per_id.items())),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("file")
    s = summarize(ap.parse_args(argv).file)
    print(f"Packets: {s['packets']}  Duration: {s['duration']:.1f}s")
    for fmt, year, major, minor, pver in s["versions"]:
        print(f"packetFormat={fmt} gameYear={year} version={major}.{minor} "
              f"packetVersion={pver}")
    print("Session UIDs: " + (", ".join(str(u) for u in s["session_uids"]) or "-"))
    print(f"{'id':>3} {'name':<20} {'count':>8} {'gaps':>6}  sizes")
    for pid, r in s["by_id"].items():
        print(f"{pid:>3} {r['name']:<20} {r['count']:>8} {r['gaps']:>6}  "
              f"{', '.join(map(str, r['sizes']))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Build a throw-away app root for the e2e tests: a consistent copy of the library DB plus a few sessions.

Usage: python make_library.py <dest> [source_root]
The source library is only ever read (SQLite backup API); nothing is written to it.
"""

from __future__ import annotations

import shutil
import sqlite3
import sys
from pathlib import Path

# Austria race (main test session), Bahrain race (Planner), and the other Austria sessions so that
# "compare to another session" finds a reference whose parquet file exists.
SOURCES = (
    "Austria_race.csv",
    "bahrain_race.csv",
    "Austria_practice.csv",
    "Austria_Q1_wet.csv",
    "Austria_Q2.csv",
    "Austria_Q3.csv",
)


def main() -> None:
    dest = Path(sys.argv[1]).resolve()
    src_root = Path(sys.argv[2] if len(sys.argv) > 2 else Path(__file__).resolve().parents[3]).resolve()
    src_db = src_root / "data" / "telemetry.db"
    if not src_db.exists():
        sys.exit(f"No library at {src_db}")
    if dest == src_root or (src_root / "data").resolve() in dest.parents:
        sys.exit("Refusing to write into the source library")
    (dest / "data" / "sessions").mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(f"file:{src_db}?mode=ro", uri=True)
    out = sqlite3.connect(str(dest / "data" / "telemetry.db"))
    try:
        src.backup(out)
        rows = out.execute(
            f"SELECT telemetry_path FROM sessions WHERE source_name IN ({','.join('?' * len(SOURCES))})", SOURCES
        ).fetchall()
    finally:
        src.close()
        out.close()
    for (rel,) in rows:
        shutil.copy2(src_root / rel, dest / rel)
    print(f"library ready at {dest} ({len(rows)} parquet files)")


if __name__ == "__main__":
    main()

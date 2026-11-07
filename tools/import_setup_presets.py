"""Import per-track baseline setups from a setup spreadsheet into ``telemetry/setup_presets_data.py``.

Usage (stdlib only, no openpyxl needed):

    .venv\\Scripts\\python.exe -m tools.import_setup_presets "D:\\Pobrane z C\\Matt212 Setups.xlsx"
    .venv\\Scripts\\python.exe -m tools.import_setup_presets <xlsx> --sheet "F1 26 Safe Setups"

Expected sheet layout (Matt212's "F1 26 Safe Setups"): a header row whose first cell is "Track", then one row per
track with the columns Aerodynamics "FW / RW", Transmission "on% / off%", Suspension Geometry "camber F / camber R /
toe F / toe R", Suspension "spring F / spring R / ARB F / ARB R / ride F / ride R", Brakes "bias% / pressure%",
Tyres (PSI) "FR / FL / RR / RL" (the in-game garage order), and an optional race-strategy column.
"""

from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from datetime import date
from pathlib import Path

NS = {
    "m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}
DEFAULT_SHEET = "F1 26 Safe Setups"
OUT = Path(__file__).resolve().parents[1] / "telemetry" / "setup_presets_data.py"

# Spreadsheet track label -> app catalogue name (telemetry.track_catalog).
TRACK_NAMES = {
    "australia": "Melbourne", "china": "Shanghai", "japan": "Suzuka", "bahrain": "Bahrain",
    "saudi arabia": "Jeddah", "miami (usa)": "Miami", "miami": "Miami", "canada": "Montreal", "monaco": "Monaco",
    "barcelona (spain)": "Barcelona", "spain": "Barcelona", "austria": "Spielberg", "britain": "Silverstone",
    "belgium": "Spa", "hungary": "Hungaroring", "netherlands": "Zandvoort", "monza (italy)": "Monza",
    "italy": "Monza", "madrid (spain)": "Madring", "madrid": "Madring", "azerbaijan": "Baku",
    "singapore": "Singapore", "texas (usa)": "Austin", "usa": "Austin", "mexico": "Mexico City",
    "brazil": "Interlagos", "las vegas (usa)": "Las Vegas", "las vegas": "Las Vegas", "qatar": "Lusail",
    "abu dhabi": "Yas Marina", "imola (italy)": "Imola", "imola": "Imola",
    "austria reverse": "Spielberg Reverse", "britain reverse": "Silverstone Reverse",
    "netherlands reverse": "Zandvoort Reverse",
}

_NUM = re.compile(r"-?\d+(?:\.\d+)?")


def read_sheet(path: Path, sheet: str) -> list[list[str]]:
    """Rows of a sheet as lists of cell strings (column letters dropped, empty cells kept as '')."""
    z = zipfile.ZipFile(path)
    shared: list[str] = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", NS):
            shared.append("".join(t.text or "" for t in si.iter(f"{{{NS['m']}}}t")))
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rels = {r.get("Id"): r.get("Target") for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
    targets = {s.get("name"): rels[s.get(f"{{{NS['r']}}}id")] for s in wb.find("m:sheets", NS)}
    if sheet not in targets:
        raise SystemExit(f"sheet {sheet!r} not found; sheets: {', '.join(targets)}")
    target = targets[sheet].lstrip("/")
    root = ET.fromstring(z.read(target if target.startswith("xl/") else f"xl/{target}"))
    rows: list[list[str]] = []
    for row in root.iter(f"{{{NS['m']}}}row"):
        cells: dict[int, str] = {}
        for c in row.findall("m:c", NS):
            col = _col_index(c.get("r") or "")
            v, typ = c.find("m:v", NS), c.get("t")
            if typ == "inlineStr":
                val = "".join(x.text or "" for x in c.iter(f"{{{NS['m']}}}t"))
            elif v is None:
                continue
            elif typ == "s":
                val = shared[int(v.text)]
            else:
                val = v.text or ""
            cells[col] = val.strip()
        if cells:
            rows.append([cells.get(i, "") for i in range(max(cells) + 1)])
    return rows


def _col_index(ref: str) -> int:
    n = 0
    for ch in re.match(r"[A-Z]+", ref).group(0):
        n = n * 26 + ord(ch) - 64
    return n - 1


def numbers(cell: str, count: int, what: str) -> list[float]:
    got = [float(x) for x in _NUM.findall(cell)]
    if len(got) != count:
        raise ValueError(f"{what}: expected {count} numbers in {cell!r}, got {got}")
    return got


def parse_row(row: list[str]) -> tuple[str, dict]:
    label = row[0].strip()
    track = TRACK_NAMES.get(label.lower())
    if not track:
        raise ValueError(f"unknown track label {label!r}")
    fw, rw = numbers(row[1], 2, f"{label} aero")
    diff_on, diff_off = numbers(row[2], 2, f"{label} transmission")
    camber_f, camber_r, toe_f, toe_r = numbers(row[3], 4, f"{label} geometry")
    spring_f, spring_r, arb_f, arb_r, ride_f, ride_r = numbers(row[4], 6, f"{label} suspension")
    bias, brake_press = numbers(row[5], 2, f"{label} brakes")
    fr, fl, rr, rl = numbers(row[6], 4, f"{label} tyres")  # garage order FR / FL / RR / RL
    strategy = row[8].strip() if len(row) > 8 else ""
    return track, {
        "label": label, "fw": fw, "rw": rw, "diff_on": diff_on / 100, "diff_off": diff_off / 100,
        "camber_f": camber_f, "camber_r": camber_r, "toe_f": toe_f, "toe_r": toe_r,
        "spring_f": spring_f, "spring_r": spring_r, "arb_f": arb_f, "arb_r": arb_r, "ride_f": ride_f, "ride_r": ride_r,
        "bias": bias / 100, "brake_press": brake_press / 100,
        "psi": [fl, fr, rl, rr],  # stored front-first FL, FR, RL, RR like the SRT arrays
        "strategy": strategy,
    }


def parse(rows: list[list[str]]) -> dict[str, dict]:
    head = next((i for i, r in enumerate(rows) if r and r[0].strip().lower() == "track"), None)
    if head is None:
        raise SystemExit("no header row starting with 'Track'")
    out: dict[str, dict] = {}
    for r in rows[head + 1:]:
        if not r or not r[0].strip() or len(r) < 7:
            continue
        track, preset = parse_row(r)
        out[track] = preset
    return out


def render(presets: dict[str, dict], source: str, sheet: str) -> str:
    lines = [
        '"""Per-track baseline setups (generated by ``tools/import_setup_presets.py`` -- do not edit by hand).',
        "",
        "Units: wings / springs / ARB / ride height in garage clicks, camber / toe in degrees, diff / brake bias /",
        "brake pressure as 0-1 fractions, ``psi`` per wheel front-first FL, FR, RL, RR.",
        '"""',
        "",
        f"SOURCE = {{'file': {source!r}, 'sheet': {sheet!r}, 'imported': {date.today().isoformat()!r}}}",
        "",
        "PRESETS: dict[str, dict] = {",
    ]
    for track in sorted(presets):
        lines.append(f"    {track!r}: {presets[track]!r},")
    lines.append("}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("xlsx", type=Path)
    ap.add_argument("--sheet", default=DEFAULT_SHEET)
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args(argv)
    presets = parse(read_sheet(args.xlsx, args.sheet))
    args.out.write_text(render(presets, args.xlsx.name, args.sheet), encoding="utf-8")
    print(f"{len(presets)} presets -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

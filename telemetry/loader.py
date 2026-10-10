"""Load and normalize SRT / F1 26 telemetry CSV/TSV exports."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

COLUMN_ALIASES: dict[str, list[str]] = {
    "lap": ["lapNum", "Lap", "CurrentLap", "lap_num", "lapIndex"],
    "throttle": ["throttle", "Throttle"],
    "brake": ["brake", "Brake"],
    "gear": ["gear", "Gear"],
    "steering": ["steering", "Steering"],
    "rpm": ["rpm", "RPM"],
    "lap_time": ["lap_time", "lap_time_s", "LapTime"],
    "lap_distance": ["lap_distance", "LapDistance", "distance"],
    "pos_x": ["world_position_X", "worldPositionX"],
    "pos_y": ["world_position_Y", "worldPositionY"],
    "pos_z": ["world_position_Z", "worldPositionZ"],
    "bin_index": ["binIndex", "bin_index"],
    "valid_bin": ["validBin", "valid_bin"],
    "track": ["trackId", "track", "Track"],
    "car": ["carId", "car", "Car"],
    "fuel": ["fuel", "Fuel"],
    "drs": ["drs", "DRS"],
}

# Tyre / corner indexing in SRT: 0=RL, 1=RR, 2=FL, 3=FR (common game convention)
TYRE_LABELS = ("RL", "RR", "FL", "FR")

# Garage channels logged in SRT exports (also persisted in compact Parquet after import)
SETUP_CHANNEL_KEYS: tuple[str, ...] = (
    "fuel_setup",
    "wing_setup_0",
    "wing_setup_1",
    "diff_onThrottle_setup",
    "diff_offThrottle_setup",
    "camber_setup_0",
    "camber_setup_1",
    "toe_setup_0",
    "toe_setup_1",
    "susp_spring_setup_0",
    "susp_spring_setup_1",
    "arb_setup_0",
    "arb_setup_1",
    "susp_height_setup_0",
    "susp_height_setup_1",
    "susp_height_setup_2",
    "susp_height_setup_3",
    "brake_bias_setup",
    "brake_press_setup",
    "front_brake_bias",
    "tyre_press_setup_0",
    "tyre_press_setup_1",
    "tyre_press_setup_2",
    "tyre_press_setup_3",
)


def list_local_csvs(folder: str | Path) -> list[Path]:
    root = Path(folder)
    if not root.exists():
        return []
    files = sorted(root.glob("*.csv")) + sorted(root.glob("*.tsv"))
    return files


def _rename_aliases(df: pd.DataFrame) -> pd.DataFrame:
    mapped: dict[str, str] = {}
    for internal, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in df.columns and internal not in df.columns:
                mapped[alias] = internal
                break
    return df.rename(columns=mapped)


def _derive_speed(df: pd.DataFrame) -> pd.DataFrame:
    if "speed" in df.columns:
        return df
    vel_cols = ["velocity_X", "velocity_Y", "velocity_Z"]
    if all(c in df.columns for c in vel_cols):
        df = df.copy()
        df["speed"] = (
            np.sqrt(
                df["velocity_X"] ** 2
                + df["velocity_Y"] ** 2
                + df["velocity_Z"] ** 2
            )
            * 3.6
        )
    return df


def _derive_helpers(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    if "gforce_X" in df.columns and "gforce_Z" in df.columns:
        # Lateral often X, longitudinal Z in these dumps — keep magnitude for GG
        df["g_lat"] = df["gforce_X"]
        df["g_long"] = df["gforce_Z"]
        df["g_mag"] = np.sqrt(df["gforce_X"] ** 2 + df["gforce_Z"] ** 2)

    if "throttle" in df.columns and "brake" in df.columns:
        df["coasting"] = (df["throttle"] < 0.02) & (df["brake"] < 0.02)
        df["trail_braking"] = (df["brake"] > 0.05) & (df["throttle"] > 0.05)

    if all(f"wheel_slip_ratio_{i}" in df.columns for i in range(4)):
        slips = df[[f"wheel_slip_ratio_{i}" for i in range(4)]]
        df["slip_max"] = slips.abs().max(axis=1)
        # Live order: 0=RL, 1=RR, 2=FL, 3=FR
        rear_slip = slips[["wheel_slip_ratio_0", "wheel_slip_ratio_1"]].abs().max(axis=1)
        front_slip = slips[["wheel_slip_ratio_2", "wheel_slip_ratio_3"]].abs().max(axis=1)
        # Lock-up heuristic under braking (front vs rear matter for bias direction)
        if "brake" in df.columns:
            braking = df["brake"] > 0.28
            df["lockup_front"] = braking & (front_slip > 0.08)
            df["lockup_rear"] = braking & (rear_slip > 0.08)
            df["lockup_risk"] = df["lockup_front"] | df["lockup_rear"]
    elif "brake" in df.columns and "slip_max" in df.columns:
        df["lockup_risk"] = (df["brake"] > 0.3) & (df["slip_max"] > 0.08)

    if "ers_store" in df.columns:
        # Normalize to MJ-ish scale for display when values are huge
        store = df["ers_store"].astype(float)
        df["ers_store_mj"] = np.where(store > 1000, store / 1e6, store)

    # Normalize cumulative energy counters when present (future imports)
    for src, dst in (
        ("ers_deployed", "ers_deployed_mj"),
        ("ers_harv_mguk", "ers_harv_mguk_mj"),
        ("ers_harv_mguh", "ers_harv_mguh_mj"),
    ):
        if src in df.columns and dst not in df.columns:
            raw = df[src].astype(float)
            df[dst] = np.where(raw.abs() > 1000, raw / 1e6, raw)

    if "lap_distance" in df.columns and "trackLength" in df.columns:
        length = df["trackLength"].replace(0, np.nan)
        df["lap_pct"] = (df["lap_distance"] / length * 100).clip(0, 100)

    return df


def load_telemetry(filepath: str | Path) -> pd.DataFrame:
    """Load a telemetry export and return a normalized DataFrame."""
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    try:
        df = pd.read_csv(path, sep="\t", engine="pyarrow")
    except Exception:
        df = pd.read_csv(path, sep="\t", on_bad_lines="skip", low_memory=False)

    return normalize_frame(df)


def normalize_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Alias columns, derive speed / helper channels, int lap. Shared by CSV load and live recording."""
    if df.empty:
        return df

    df = _rename_aliases(df)
    df = _derive_speed(df)
    df = _derive_helpers(df)

    if "lap" in df.columns:
        df = df.dropna(subset=["lap"])
        df["lap"] = df["lap"].astype(int)

    # Prefer valid bins when present (distance-aligned samples)
    if "valid_bin" in df.columns:
        # Keep invalid bins but flag them; many exports mark edges oddly
        df["valid_bin"] = df["valid_bin"].fillna(1).astype(int)

    return df.reset_index(drop=True)


def _stable_setup_value(series: pd.Series) -> float:
    """
    Robust garage value for a telemetry column.

    SRT exports often log 0 on the first rows before setup channels settle;
    median of the non-zero bulk matches what you had in the garage.
    """
    s = pd.to_numeric(series, errors="coerce").dropna()
    if s.empty:
        raise ValueError("empty setup series")
    if len(s) == 1:
        return float(s.iloc[0])
    nonzero = s[s.abs() > 1e-9]
    if len(nonzero) >= max(3, len(s) // 25):
        s = nonzero
    return float(s.median())


def mean_setup(df: pd.DataFrame) -> dict[str, float | int | str]:
    """Extract representative setup values from a session/lap slice."""
    keys: Iterable[str] = SETUP_CHANNEL_KEYS
    out: dict[str, float | int | str] = {}
    for key in keys:
        if key in df.columns:
            val = df[key].dropna()
            if not val.empty:
                try:
                    out[key] = _stable_setup_value(val)
                except ValueError:
                    continue
    if "tyre_compound_0" in df.columns:
        tc = df["tyre_compound_0"].dropna()
        if not tc.empty:
            out["tyre_compound"] = int(_stable_setup_value(tc))
    return out


def telemetry_setup_keys(df: pd.DataFrame) -> list[str]:
    """Setup columns present in this dataframe."""
    return [k for k in SETUP_CHANNEL_KEYS if k in df.columns]


def has_telemetry_setup(df: pd.DataFrame | None, *, min_keys: int = 6) -> bool:
    """True when the export carries enough garage channels to trust."""
    if df is None or df.empty:
        return False
    return len(telemetry_setup_keys(df)) >= min_keys


def _non_reset_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Drop rows where the garage channels read the post-session reset (both wings at 0)."""
    if "wing_setup_0" in df.columns and "wing_setup_1" in df.columns:
        w0 = pd.to_numeric(df["wing_setup_0"], errors="coerce").fillna(0.0)
        w1 = pd.to_numeric(df["wing_setup_1"], errors="coerce").fillna(0.0)
        return df.loc[~((w0 <= 0) & (w1 <= 0))]
    return df


def is_reset_setup(setup: dict[str, float] | None) -> bool:
    """
    True for the garbage garage the game logs after a session ends / on warm-up rows:
    both wings at 0, or several key parameters pinned at their garage minimum.
    """
    if not setup:
        return False
    from .setup_tweaker import SETUP_PARAMS

    fw, rw = setup.get("wing_setup_0"), setup.get("wing_setup_1")
    if fw is not None and rw is not None and float(fw) <= 0 and float(rw) <= 0:
        return True
    mins = {p.key: p.min_v for p in SETUP_PARAMS}
    pinned = 0
    for key in ("susp_spring_setup_0", "susp_spring_setup_1", "arb_setup_0", "arb_setup_1", "diff_onThrottle_setup"):
        if key in setup and abs(float(setup[key]) - mins[key]) < 1e-6:
            pinned += 1
    return pinned >= 3


def setup_from_telemetry(df: pd.DataFrame, lap: int | None = None) -> dict[str, float]:
    """
    Garage dict read from setup channels on the focus lap (or whole session).

    The last (incomplete) lap of an export logs a reset garage; those rows are skipped and,
    if the lap has nothing else, the nearest earlier lap with a real garage is used instead.
    """
    from .setup_tweaker import normalize_setup

    if df is None or df.empty or not has_telemetry_setup(df):
        return {}
    clean = _non_reset_rows(df)
    if clean.empty:
        return {}
    if lap is None or "lap" not in df.columns:
        return normalize_setup(mean_setup(clean))

    candidates = [clean[clean["lap"] == lap]]
    others = sorted((int(x) for x in clean["lap"].unique() if int(x) != int(lap)), key=lambda x: (abs(x - int(lap)), x))
    earlier = [x for x in others if x < int(lap)]
    later = [x for x in others if x > int(lap)]
    for other in earlier + later:
        candidates.append(clean[clean["lap"] == other])
    for sl in candidates:
        if sl.empty:
            continue
        setup = normalize_setup(mean_setup(sl))
        if setup and not is_reset_setup(setup):
            return setup
    return normalize_setup(mean_setup(clean))


def _is_missing_setup_value(key: str, value: float | None) -> bool:
    from .setup_tweaker import SETUP_PARAMS

    if value is None:
        return True
    v = float(value)
    if key.startswith("wing_setup"):
        return v <= 0
    for p in SETUP_PARAMS:
        if p.key == key:
            return v < p.min_v - 1e-6
    return False


def resolve_session_setup(
    stored: dict[str, Any] | None,
    df: pd.DataFrame | None = None,
    lap: int | None = None,
    *,
    typical_setup: dict[str, float] | None = None,
) -> tuple[dict[str, float], str]:
    """
    Merge stored setup_json with live telemetry garage channels.

    Per-lap telemetry wins when present — that's the setup the car actually ran.
    """
    from .setup_tweaker import normalize_setup

    tel = setup_from_telemetry(df, lap) if has_telemetry_setup(df) else {}
    stored_n = normalize_setup(stored or {})

    if tel:
        merged = dict(stored_n)
        merged.update(tel)
        if lap is not None:
            source = f"telemetry lap {lap}"
        else:
            source = "telemetry"
    elif stored_n:
        merged = dict(stored_n)
        source = "imported setup_json"
    else:
        merged = {}
        source = "none"

    if typical_setup:
        for key, val in typical_setup.items():
            cur = merged.get(key)
            if key not in merged or _is_missing_setup_value(key, cur):
                merged[key] = float(val)

    if "brake_bias_setup" in merged:
        merged.setdefault("front_brake_bias", merged["brake_bias_setup"])

    return normalize_setup(merged), source


def repair_setup_from_telemetry(
    setup: dict[str, Any] | None,
    df: pd.DataFrame | None = None,
    lap: int | None = None,
    *,
    typical_setup: dict[str, float] | None = None,
) -> dict[str, float]:
    """Backfill missing/zeroed garage keys from lap telemetry or track typical."""
    resolved, _ = resolve_session_setup(setup, df, lap, typical_setup=typical_setup)
    return resolved

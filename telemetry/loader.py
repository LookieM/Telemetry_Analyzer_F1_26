"""Load and normalize SRT / F1 26 telemetry CSV/TSV exports."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

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
        # Lock-up heuristic under braking
        if "brake" in df.columns:
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


def mean_setup(df: pd.DataFrame) -> dict[str, float | int | str]:
    """Extract representative setup values from a session/lap slice."""
    keys: Iterable[str] = [
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
    ]
    out: dict[str, float | int | str] = {}
    for key in keys:
        if key in df.columns:
            val = df[key].dropna()
            if not val.empty:
                out[key] = float(val.iloc[0])
    if "tyre_compound_0" in df.columns:
        out["tyre_compound"] = int(df["tyre_compound_0"].dropna().iloc[0])
    return out

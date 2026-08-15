"""Lap metrics, alignment, and time-delta calculations."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .loader import mean_setup


MIN_VALID_LAP_S = 25.0


def session_meta(df: pd.DataFrame) -> dict:
    meta = {
        "track": None,
        "car": None,
        "samples": len(df),
        "laps": int(df["lap"].nunique()) if "lap" in df.columns else 0,
        "track_length": None,
    }
    if "track" in df.columns and not df["track"].empty:
        meta["track"] = str(df["track"].iloc[0])
    if "car" in df.columns and not df["car"].empty:
        meta["car"] = str(df["car"].iloc[0])
    if "trackLength" in df.columns:
        meta["track_length"] = float(df["trackLength"].iloc[0])
    return meta


def _lap_end_time(lap_df: pd.DataFrame) -> float | None:
    if "lap_time" not in lap_df.columns or lap_df.empty:
        return None
    t = float(lap_df["lap_time"].max())
    return t if t >= MIN_VALID_LAP_S else None


def build_lap_summary(df: pd.DataFrame) -> pd.DataFrame:
    """One row per lap with pace, fuel, tyres, ERS, and input stats."""
    if "lap" not in df.columns:
        return pd.DataFrame()

    rows = []
    for lap, lap_df in df.groupby("lap"):
        lap_time = _lap_end_time(lap_df)
        if lap_time is None:
            continue

        row: dict = {
            "lap": int(lap),
            "lap_time": lap_time,
            "samples": len(lap_df),
        }

        if "speed" in lap_df.columns:
            row["vmax"] = float(lap_df["speed"].max())
            row["vavg"] = float(lap_df["speed"].mean())

        if "throttle" in lap_df.columns:
            row["throttle_full_pct"] = float((lap_df["throttle"] > 0.98).mean() * 100)
            row["throttle_avg"] = float(lap_df["throttle"].mean() * 100)

        if "brake" in lap_df.columns:
            row["brake_pct"] = float((lap_df["brake"] > 0.05).mean() * 100)
            row["brake_max"] = float(lap_df["brake"].max())

        if "coasting" in lap_df.columns:
            row["coast_pct"] = float(lap_df["coasting"].mean() * 100)

        if "fuel" in lap_df.columns:
            row["fuel_start"] = float(lap_df["fuel"].iloc[0])
            row["fuel_end"] = float(lap_df["fuel"].iloc[-1])
            row["fuel_used"] = row["fuel_start"] - row["fuel_end"]

        if "tyre_wear_0" in lap_df.columns:
            wears = [float(lap_df[f"tyre_wear_{i}"].iloc[-1]) for i in range(4) if f"tyre_wear_{i}" in lap_df.columns]
            if wears:
                row["tyre_wear_avg"] = float(np.mean(wears) * 100)
                row["tyre_wear_max"] = float(np.max(wears) * 100)

        if "tyre_temp_0" in lap_df.columns:
            temps = [float(lap_df[f"tyre_temp_{i}"].mean()) for i in range(4) if f"tyre_temp_{i}" in lap_df.columns]
            if temps:
                row["tyre_temp_avg"] = float(np.mean(temps))

        if "tyre_compound_0" in lap_df.columns:
            row["compound"] = int(lap_df["tyre_compound_0"].iloc[0])

        if "ers_store_mj" in lap_df.columns:
            row["ers_start_mj"] = float(lap_df["ers_store_mj"].iloc[0])
            row["ers_end_mj"] = float(lap_df["ers_store_mj"].iloc[-1])
        elif "ers_store" in lap_df.columns:
            store = lap_df["ers_store"].astype(float)
            scale = 1e6 if store.max() > 1000 else 1.0
            row["ers_start_mj"] = float(store.iloc[0] / scale)
            row["ers_end_mj"] = float(store.iloc[-1] / scale)

        if "ers_deployed" in lap_df.columns:
            dep = lap_df["ers_deployed"].astype(float)
            scale = 1e6 if dep.max() > 1000 else 1.0
            row["ers_deployed_mj"] = float((dep.max() - dep.min()) / scale) if len(dep) else 0.0

        if "drs" in lap_df.columns:
            row["drs_pct"] = float((lap_df["drs"] > 0).mean() * 100)

        if "lockup_risk" in lap_df.columns:
            row["lockup_samples"] = int(lap_df["lockup_risk"].sum())

        if "g_mag" in lap_df.columns:
            row["g_peak"] = float(lap_df["g_mag"].max())

        rows.append(row)

    summary = pd.DataFrame(rows)
    if summary.empty:
        return summary

    summary = summary.sort_values("lap").reset_index(drop=True)
    best = summary["lap_time"].min()
    summary["delta_best"] = summary["lap_time"] - best
    summary["is_best"] = summary["lap_time"] == best
    return summary


def _distance_key(df: pd.DataFrame) -> str:
    if "bin_index" in df.columns:
        return "bin_index"
    if "lap_distance" in df.columns:
        return "lap_distance"
    raise ValueError("Need bin_index or lap_distance to align laps")


def get_lap(df: pd.DataFrame, lap: int) -> pd.DataFrame:
    out = df[df["lap"] == lap].copy()
    key = _distance_key(out) if not out.empty else "lap_distance"
    if key in out.columns:
        out = out.sort_values(key)
        out = out.drop_duplicates(subset=[key], keep="last")
    return out.reset_index(drop=True)


def align_laps(
    ref: pd.DataFrame,
    cmp: pd.DataFrame,
    channels: list[str] | None = None,
) -> pd.DataFrame:
    """Align comparison lap onto reference distance grid via interpolation."""
    if ref.empty or cmp.empty:
        return pd.DataFrame()

    key = _distance_key(ref)
    if key not in cmp.columns:
        raise ValueError(f"Comparison lap missing {key}")

    ref = ref.sort_values(key).drop_duplicates(subset=[key], keep="last")
    cmp = cmp.sort_values(key).drop_duplicates(subset=[key], keep="last")

    x_ref = ref[key].to_numpy(dtype=float)
    x_cmp = cmp[key].to_numpy(dtype=float)

    default_channels = [
        "lap_time",
        "speed",
        "throttle",
        "brake",
        "gear",
        "steering",
        "rpm",
        "fuel",
        "drs",
        "g_lat",
        "g_long",
        "ers_store_mj",
        "ers_deployMode",
        "slip_max",
    ]
    channels = channels or default_channels

    out = pd.DataFrame({key: x_ref})
    if "lap_distance" in ref.columns:
        out["lap_distance"] = ref["lap_distance"].to_numpy()
    # SRT / F1 26: X/Y are the track plane; Z is height
    if "pos_x" in ref.columns and "pos_y" in ref.columns:
        out["pos_x"] = ref["pos_x"].to_numpy()
        out["pos_y"] = ref["pos_y"].to_numpy()
    elif "pos_x" in ref.columns and "pos_z" in ref.columns:
        out["pos_x"] = ref["pos_x"].to_numpy()
        out["pos_y"] = ref["pos_z"].to_numpy()

    for ch in channels:
        if ch in ref.columns:
            out[f"ref_{ch}"] = ref[ch].to_numpy(dtype=float)
        if ch in cmp.columns:
            y = cmp[ch].to_numpy(dtype=float)
            out[f"cmp_{ch}"] = np.interp(x_ref, x_cmp, y)

    return out


def compute_time_delta(aligned: pd.DataFrame) -> pd.DataFrame:
    """Positive delta => comparison is slower than reference at that point."""
    out = aligned.copy()
    if "ref_lap_time" in out.columns and "cmp_lap_time" in out.columns:
        out["delta_time"] = out["cmp_lap_time"] - out["ref_lap_time"]
        out["delta_gain"] = -out["delta_time"].diff().fillna(0)
    elif "ref_speed" in out.columns and "cmp_speed" in out.columns and "lap_distance" in out.columns:
        # Fallback: integrate ds/v difference
        ds = out["lap_distance"].diff().fillna(0).clip(lower=0)
        v_ref = (out["ref_speed"] / 3.6).replace(0, np.nan)
        v_cmp = (out["cmp_speed"] / 3.6).replace(0, np.nan)
        dt = ds / v_cmp - ds / v_ref
        out["delta_time"] = dt.fillna(0).cumsum()
        out["delta_gain"] = -dt.fillna(0)
    else:
        out["delta_time"] = 0.0
        out["delta_gain"] = 0.0
    return out


def sector_deltas(aligned: pd.DataFrame, n_sectors: int = 3) -> pd.DataFrame:
    """Split lap into N equal distance sectors and sum time gained/lost."""
    if aligned.empty or "delta_time" not in aligned.columns:
        return pd.DataFrame()

    dist_col = "lap_distance" if "lap_distance" in aligned.columns else aligned.columns[0]
    d = aligned[dist_col]
    d0, d1 = float(d.min()), float(d.max())
    if d1 <= d0:
        return pd.DataFrame()

    edges = np.linspace(d0, d1, n_sectors + 1)
    rows = []
    for i in range(n_sectors):
        mask = (d >= edges[i]) & (d <= edges[i + 1] if i == n_sectors - 1 else d < edges[i + 1])
        chunk = aligned.loc[mask]
        if chunk.empty:
            continue
        start_delta = float(chunk["delta_time"].iloc[0])
        end_delta = float(chunk["delta_time"].iloc[-1])
        rows.append(
            {
                "sector": i + 1,
                "dist_start": float(edges[i]),
                "dist_end": float(edges[i + 1]),
                "delta_s": end_delta - start_delta,
                "delta_end": end_delta,
            }
        )
    return pd.DataFrame(rows)


def mini_sector_table(aligned: pd.DataFrame, n: int = 20) -> pd.DataFrame:
    return sector_deltas(aligned, n_sectors=n).rename(columns={"sector": "mini_sector"})


def setup_snapshot(df: pd.DataFrame, lap: int | None = None) -> dict:
    slice_df = df if lap is None else df[df["lap"] == lap]
    return mean_setup(slice_df)

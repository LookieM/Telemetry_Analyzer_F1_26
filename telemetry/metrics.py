"""Lap metrics, alignment, and time-delta calculations."""

from __future__ import annotations

import threading

import numpy as np
import pandas as pd

from .loader import mean_setup


# Absolute floor/ceiling for a completed F1 26 flying lap.
# Takebacks / red-flag partials often land ~20–40s and must not become PBs.
MIN_VALID_LAP_S = 45.0
MAX_VALID_LAP_S = 240.0
# Incomplete lap: covered distance vs track length (or absolute metres).
MIN_LAP_DISTANCE_FRAC = 0.72
MIN_LAP_DISTANCE_M = 2200.0
MIN_LAP_SAMPLES = 250
# Relative to session median — catches short outliers when length is unknown.
MIN_REL_MEDIAN = 0.68
MAX_REL_MEDIAN = 1.85
# Lap-time cost of carrying fuel (matches the fuel term in setup_tweaker).
FUEL_S_PER_KG = 0.030

# Lap classes ("lap_class" in build_lap_summary): start | push | in | pit | out | sc | slow | invalid.
# Laps are labelled, never dropped — each consumer skips what it cannot use.
LAP_CLASSES = ("start", "push", "in", "pit", "out", "sc", "slow", "invalid")
# Share of a lap behind the safety car / VSC that makes it an "sc" lap.
SC_LAP_SHARE = 0.25
# Mean tyre wear falling this much inside a lap, to near zero, means a new set was fitted.
NEW_SET_WEAR_DROP_PP = 5.0
NEW_SET_WEAR_LEFT_PP = 4.0
# A race stop costs time; a garage tyre change between practice runs does not.
SLOW_LAP_FACTOR = 1.07
# Share of samples with compound / fuel < 0 (pre-start or post-session garbage).
INVALID_SAMPLE_SHARE = 0.4
STANDING_START_KMH = 30.0


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


def fuel_corrected_time(
    lap_time: float,
    fuel_kg: float | None,
    ref_kg: float = 5.0,
    s_per_kg: float = FUEL_S_PER_KG,
) -> float:
    """Lap time re-expressed at `ref_kg` of fuel; unchanged when the fuel reading is unusable."""
    if fuel_kg is None or not np.isfinite(fuel_kg) or fuel_kg <= 0:
        return float(lap_time)
    return float(lap_time) - (float(fuel_kg) - float(ref_kg)) * float(s_per_kg)


def _lap_end_time(lap_df: pd.DataFrame) -> float | None:
    if "lap_time" not in lap_df.columns or lap_df.empty:
        return None
    t = float(lap_df["lap_time"].max())
    if not np.isfinite(t):
        return None
    return t


def _track_length_hint(df: pd.DataFrame, track_length: float | None = None) -> float | None:
    if track_length is not None and float(track_length) > 500:
        return float(track_length)
    if "trackLength" in df.columns and not df["trackLength"].empty:
        try:
            v = float(df["trackLength"].iloc[0])
            if v > 500:
                return v
        except (TypeError, ValueError):
            pass
    return None


def is_probable_lap(
    lap_df: pd.DataFrame,
    lap_time: float | None,
    *,
    track_length: float | None = None,
) -> bool:
    """
    True for a completed flying lap; False for takebacks, red-flag partials,
    and other telemetry glitches that produce absurdly short times.
    """
    if lap_time is None or not np.isfinite(lap_time):
        return False
    if lap_time < MIN_VALID_LAP_S or lap_time > MAX_VALID_LAP_S:
        return False
    if len(lap_df) < MIN_LAP_SAMPLES:
        return False

    if "lap_distance" in lap_df.columns and not lap_df.empty:
        dmax = float(np.nanmax(lap_df["lap_distance"].to_numpy(dtype=float)))
        if not np.isfinite(dmax):
            return False
        length = track_length
        if length is not None and length > 500:
            if dmax < MIN_LAP_DISTANCE_FRAC * float(length):
                return False
        elif dmax < MIN_LAP_DISTANCE_M:
            return False

    return True


def _apply_relative_probable_mask(times: pd.Series) -> pd.Series:
    """Drop short/long outliers vs session median when enough laps exist."""
    ok = pd.Series(True, index=times.index)
    if len(times) < 3:
        return ok
    med = float(times.median())
    if not np.isfinite(med) or med <= 0:
        return ok
    ok &= times >= med * MIN_REL_MEDIAN
    ok &= times <= med * MAX_REL_MEDIAN
    return ok


def _first_valid_int(series: pd.Series, last: bool = False) -> int | None:
    v = series.to_numpy(dtype=float, na_value=np.nan)
    v = v[v >= 0]
    if not v.size:
        return None
    return int(v[-1] if last else v[0])


def _col(frame: pd.DataFrame, name: str) -> np.ndarray:
    return frame[name].to_numpy(dtype=float, na_value=np.nan)


def _span(mask: np.ndarray) -> tuple[float, float]:
    """(first, last) position of True values as a fraction of the lap, NaN when none."""
    idx = np.flatnonzero(mask)
    if not idx.size:
        return np.nan, np.nan
    return idx[0] / len(mask), idx[-1] / len(mask)


def _mode(values: np.ndarray) -> float:
    v = values[np.isfinite(values)]
    if not v.size:
        return np.nan
    uniq, counts = np.unique(v, return_counts=True)
    return float(uniq[np.argmax(counts)])


def _lap_flags(lap_df: pd.DataFrame) -> dict:
    """
    Raw per-lap signals for classification (chronological, garbage rows removed): garbage share,
    start speed, where a new tyre set appears, and — when the export logs them — the game's own
    pit / tyre-age / safety-car / weather channels.
    """
    n = len(lap_df)
    order = np.argsort(_col(lap_df, "lap_time"), kind="stable") if "lap_time" in lap_df.columns else np.arange(n)
    bad = np.zeros(n, dtype=bool)
    for name in ("tyre_compound_0", "fuel"):
        if name in lap_df.columns:
            bad |= _col(lap_df, name) < 0
    good = order[~bad[order]]  # garbage rows carry lap_time ~0 and would pose as the lap start
    flags = {
        "_bad_share": float(bad.mean()) if n else 0.0,
        "_v_start": np.nan,
        "_reset_at": np.nan,  # fraction of the lap at which a new tyre set appears
        "_stop_s": np.nan,
        "_lane_first": np.nan,
        "_lane_last": np.nan,
        "_sc_share": np.nan,
        "_age_start": np.nan,
        "tyre_age": np.nan,  # game tyre age at the end of the lap (laps on this set)
    }
    if not good.size:
        return flags

    def chan(name: str) -> np.ndarray | None:
        return _col(lap_df, name)[good] if name in lap_df.columns else None

    if (speed := chan("speed")) is not None:
        flags["_v_start"] = float(speed[0])

    age = chan("tyres_age")
    if age is not None and np.isfinite(age).any():
        a = age[np.isfinite(age) & (age >= 0)]
        if a.size:
            flags["_age_start"], flags["tyre_age"] = float(a[0]), float(a[-1])
            drop = np.flatnonzero(np.diff(a) < 0)
            if drop.size:
                flags["_reset_at"] = float(drop[0] + 1) / len(a)
    else:
        wear_cols = [f"tyre_wear_{i}" for i in range(4) if f"tyre_wear_{i}" in lap_df.columns]
        if wear_cols:
            w = np.column_stack([_col(lap_df, c) for c in wear_cols])[good]
            ok = (w >= 0).all(axis=1)
            wear = w[ok].mean(axis=1) * 100
            if len(wear) >= 2:
                fall = np.maximum.accumulate(wear) - wear
                i = int(np.argmax(fall))
                if fall[i] >= NEW_SET_WEAR_DROP_PP and wear[i:].min() <= NEW_SET_WEAR_LEFT_PP:
                    flags["_reset_at"] = float(np.argmax(fall >= NEW_SET_WEAR_DROP_PP)) / len(wear)

    if (stop := chan("pitStopTime")) is not None:
        flags["_stop_s"] = float(np.nanmax(stop)) if np.isfinite(stop).any() else 0.0
    if (status := chan("pit_status")) is not None:
        flags["_lane_first"], flags["_lane_last"] = _span(status > 0)
    if (sc := chan("safetyCarStatus")) is not None:
        flags["_sc_share"] = float((sc > 0).mean())
    if (wx := chan("weather")) is not None:
        flags["weather"] = _mode(wx)
    for name, key in (("track_temp", "track_temp"), ("air_temp", "air_temp")):
        if (v := chan(name)) is not None and np.isfinite(v).any():
            flags[key] = float(np.nanmean(v))
    if (inv := chan("lap_time_invalid")) is not None:
        flags["track_limits"] = bool(np.nanmax(inv) > 0) if np.isfinite(inv).any() else False
    return flags


def _classify_laps(summary: pd.DataFrame) -> pd.DataFrame:
    """
    Add lap_class, pit_stop and fresh_set (first lap on a new tyre set) to a lap summary.

    With the game's channels (tyres_age, pitStopTime, pit_status, safetyCarStatus) those decide:
    a stop is a lap with a pit-box stop, a new set is a drop in tyre age (also across laps the
    export skipped), in / out laps are the pit-lane time at the end / start of a lap.
    Older exports fall back to a wear reset plus a >= 7% lap-time loss; there the previous lap is
    the in-lap when the set appears early in the lap (line in the pit lane, e.g. Bahrain) and the
    next lap the out-lap when it appears late (e.g. Monaco).
    """
    out = summary.copy()
    n = len(out)

    def col(name: str) -> np.ndarray:
        return out[name].to_numpy(dtype=float) if name in out.columns else np.full(n, np.nan)

    laps = out["lap"].astype(int).to_numpy()
    times = out["lap_time"].to_numpy(dtype=float)
    cls = np.array(["push"] * n, dtype=object)
    cls[np.nan_to_num(col("_bad_share")) >= INVALID_SAMPLE_SHARE] = "invalid"
    lane_first = col("_lane_first")
    lane_last = col("_lane_last")
    v0 = col("_v_start")
    starts_in_lane = np.isfinite(lane_first) & (lane_first <= 0.05)
    from_standstill = (cls == "push") & (v0 < STANDING_START_KMH) & ~starts_in_lane
    # Only the first real lap is a race start; a standstill later (red flag, export gap) is just slow.
    real = np.flatnonzero(cls != "invalid")
    first_real = int(real[0]) if real.size else -1
    cls[from_standstill & (np.arange(n) == first_real)] = "start"
    cls[from_standstill & (np.arange(n) != first_real)] = "slow"
    reset_at = col("_reset_at")
    stop_s = col("_stop_s")
    age_start = col("_age_start")
    age_end = col("tyre_age")
    has_age = bool(np.isfinite(age_end).any())
    has_stop_timer = bool(np.isfinite(stop_s).any())
    push = cls == "push"
    base = float(np.median(times[push & np.isnan(reset_at)])) if (push & np.isnan(reset_at)).any() else np.nan

    pit = np.zeros(n, dtype=bool)
    fresh = np.zeros(n, dtype=bool)

    def neighbour(i: int, step: int) -> int | None:
        j = i + step
        return j if 0 <= j < n and laps[j] == laps[i] + step else None

    if has_age:
        for i in range(n):
            late = np.isfinite(reset_at[i]) and reset_at[i] >= 0.5
            if np.isfinite(reset_at[i]):
                j = neighbour(i, 1) if late else i
                if j is not None:
                    fresh[j] = True
            elif i and np.isfinite(age_start[i]) and np.isfinite(age_end[i - 1]) and age_start[i] < age_end[i - 1]:
                fresh[i] = True  # the set changed on a lap the export skipped
            stopped = (has_stop_timer and stop_s[i] > 0) or (
                not has_stop_timer and np.isfinite(reset_at[i]) and np.isfinite(base) and times[i] >= SLOW_LAP_FACTOR * base
            )
            if stopped and cls[i] != "invalid":
                cls[i], pit[i] = "pit", True
        # Pit-lane time without a stop on that lap: entry at the end (in), exit at the start (out),
        # or the whole lane on one lap (drive-through).
        for i in np.flatnonzero(np.isfinite(lane_first) & ~pit):
            if cls[i] == "invalid":
                continue
            if lane_first[i] >= 0.5:
                cls[i] = "in"
            elif lane_last[i] <= 0.5:
                cls[i] = "out"
            else:
                cls[i] = "pit"
    else:
        for i in np.flatnonzero(~np.isnan(reset_at)):
            early = reset_at[i] < 0.5
            j = i if early else neighbour(i, 1)
            if j is not None:
                fresh[j] = True
            if cls[i] != "invalid" and np.isfinite(base) and times[i] >= SLOW_LAP_FACTOR * base:
                cls[i], pit[i] = "pit", True
                k = neighbour(i, -1) if early else neighbour(i, 1)
                if k is not None and cls[k] == "push":
                    cls[k] = "in" if early else "out"

    sc_share = col("_sc_share")
    cls[(cls == "push") & np.isfinite(sc_share) & (sc_share >= SC_LAP_SHARE)] = "sc"

    if "compound" in out.columns:
        comp = pd.to_numeric(out["compound"], errors="coerce").to_numpy(dtype=float)
        for i in range(1, n):
            if laps[i] == laps[i - 1] + 1 and comp[i] != comp[i - 1] and comp[i] >= 0 and comp[i - 1] >= 0:
                if not fresh[i] and not fresh[i - 1]:
                    fresh[i] = True

    push = cls == "push"
    if push.any():
        ref = float(np.median(times[push]))
        cls[push & (times > SLOW_LAP_FACTOR * ref)] = "slow"

    out["lap_class"] = cls
    out["pit_stop"] = pit
    out["fresh_set"] = fresh
    return out.drop(columns=[c for c in out.columns if c.startswith("_")])


# The UI asks for the same session's summary dozens of times per rerun (coach, diagnosis,
# stint windows, tyres...). Results are memoised per DataFrame object and handed out as copies.
_SUMMARY_CACHE: list[tuple[pd.DataFrame, float | None, int, pd.DataFrame]] = []
_SUMMARY_CACHE_SIZE = 6
_SUMMARY_LOCK = threading.Lock()


def build_lap_summary(df: pd.DataFrame, track_length: float | None = None) -> pd.DataFrame:
    """
    One row per probable lap with pace, fuel, tyres, ERS, and input stats.

    Each lap also carries lap_class / pit_stop / fresh_set (see _classify_laps).
    """
    with _SUMMARY_LOCK:
        for cached_df, cached_len, n_rows, result in _SUMMARY_CACHE:
            if cached_df is df and cached_len == track_length and n_rows == len(df):
                return result.copy()
    result = _build_lap_summary(df, track_length)
    with _SUMMARY_LOCK:
        _SUMMARY_CACHE.insert(0, (df, track_length, len(df), result))
        del _SUMMARY_CACHE[_SUMMARY_CACHE_SIZE:]
    return result.copy()


def _build_lap_summary(df: pd.DataFrame, track_length: float | None = None) -> pd.DataFrame:
    if "lap" not in df.columns:
        return pd.DataFrame()

    length = _track_length_hint(df, track_length)
    rows = []
    for lap, lap_df in df.groupby("lap"):
        lap_time = _lap_end_time(lap_df)
        if not is_probable_lap(lap_df, lap_time, track_length=length):
            continue

        row: dict = {
            "lap": int(lap),
            "lap_time": float(lap_time),
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
            # First / last real value: exports pad lap edges with -1 garbage.
            first = _first_valid_int(lap_df["tyre_compound_0"])
            last = _first_valid_int(lap_df["tyre_compound_0"], last=True)
            row["compound"] = first if first is not None else -1
            row["compound_end"] = last if last is not None else -1

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

        row.update(_lap_flags(lap_df))
        rows.append(row)

    summary = pd.DataFrame(rows)
    if summary.empty:
        return summary

    summary = summary.sort_values("lap").reset_index(drop=True)
    rel_ok = _apply_relative_probable_mask(summary["lap_time"])
    summary = summary.loc[rel_ok].reset_index(drop=True)
    if summary.empty:
        return summary

    summary = _classify_laps(summary)
    valid = summary["lap_class"] != "invalid"
    best = summary.loc[valid, "lap_time"].min() if valid.any() else summary["lap_time"].min()
    summary["delta_best"] = summary["lap_time"] - best
    summary["is_best"] = summary["lap_time"] == best
    return summary


def _distance_key(df: pd.DataFrame) -> str:
    if "bin_index" in df.columns:
        return "bin_index"
    if "lap_distance" in df.columns:
        return "lap_distance"
    raise ValueError("Need bin_index or lap_distance to align laps")


# get_lap is called hundreds of times per rerun on the same session frame; lap positions and the
# prepared (sorted, de-duplicated) slices are memoised per frame object, handed out as copies.
_LAP_CACHE: list[tuple[pd.DataFrame, int, dict[int, np.ndarray], dict[int, pd.DataFrame]]] = []
_LAP_CACHE_SIZE = 4
_LAP_LOCK = threading.Lock()


def _prepare_lap(out: pd.DataFrame) -> pd.DataFrame:
    key = _distance_key(out) if not out.empty else "lap_distance"
    if key in out.columns:
        out = out.sort_values(key)
        out = out.drop_duplicates(subset=[key], keep="last")
    return out.reset_index(drop=True)


def get_lap(df: pd.DataFrame, lap: int) -> pd.DataFrame:
    if "lap" not in df.columns:
        return _prepare_lap(df.iloc[0:0].copy())
    with _LAP_LOCK:
        entry = next((e for e in _LAP_CACHE if e[0] is df and e[1] == len(df)), None)
        if entry is None:
            positions = {int(k): v for k, v in df.groupby("lap", sort=False).indices.items()}
            entry = (df, len(df), positions, {})
            _LAP_CACHE.insert(0, entry)
            del _LAP_CACHE[_LAP_CACHE_SIZE:]
        _, _, positions, prepared = entry
        lap = int(lap)
        if lap not in prepared:
            idx = positions.get(lap)
            prepared[lap] = _prepare_lap(df.iloc[idx] if idx is not None else df.iloc[0:0])
        return prepared[lap].copy()


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


def sample_at_distance(lap_df: pd.DataFrame, distance: float) -> dict:
    """Nearest telemetry sample to a lap distance (for cursor readout)."""
    if lap_df.empty or "lap_distance" not in lap_df.columns:
        return {}
    dist = lap_df["lap_distance"].to_numpy(dtype=float)
    idx = int(np.argmin(np.abs(dist - float(distance))))
    row = lap_df.iloc[idx]
    out: dict = {"distance": float(row["lap_distance"]), "index": idx}
    for key in ("speed", "throttle", "brake", "gear", "steering", "lap_time", "rpm", "fuel"):
        if key in lap_df.columns and pd.notna(row[key]):
            out[key] = float(row[key])
    return out


def setup_snapshot(df: pd.DataFrame, lap: int | None = None) -> dict:
    from .loader import setup_from_telemetry

    snap = setup_from_telemetry(df, lap)
    if snap:
        return snap
    slice_df = df if lap is None else df[df["lap"] == lap]
    return mean_setup(slice_df)

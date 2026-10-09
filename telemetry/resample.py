"""Pure numpy/pandas helpers for putting laps on a shared distance grid."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd


def resample_by_distance(
    lap_df: pd.DataFrame,
    channels: Sequence[str],
    grid: np.ndarray,
    *,
    x_col: str = "lap_distance",
) -> dict[str, np.ndarray]:
    """Channels of one lap interpolated onto a shared distance grid (NaN outside the lap)."""
    out: dict[str, np.ndarray] = {}
    if lap_df.empty or x_col not in lap_df.columns:
        return {c: np.full(len(grid), np.nan) for c in channels}
    d = lap_df[[x_col, *[c for c in channels if c in lap_df.columns]]].dropna(subset=[x_col])
    d = d.sort_values(x_col).drop_duplicates(subset=[x_col], keep="last")
    xs = d[x_col].to_numpy(dtype=float)
    for c in channels:
        if c not in d.columns or len(xs) < 2:
            out[c] = np.full(len(grid), np.nan)
            continue
        ys = pd.to_numeric(d[c], errors="coerce").to_numpy(dtype=float)
        ok = np.isfinite(ys)
        if ok.sum() < 2:
            out[c] = np.full(len(grid), np.nan)
            continue
        vals = np.interp(grid, xs[ok], ys[ok], left=np.nan, right=np.nan)
        out[c] = vals
    return out


def distance_grid(length_m: float, step_m: float = 2.0) -> np.ndarray:
    """Evenly spaced distances 0..length_m (inclusive of the last step)."""
    return np.arange(0.0, float(length_m) + step_m, step_m)

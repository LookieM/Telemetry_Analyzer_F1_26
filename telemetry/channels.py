"""Channel registry: canonical names, units and groups for export channels (incl. per-wheel)."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

# SRT / F1 26 per-wheel index order (same as loader.TYRE_LABELS).
WHEELS = ("RL", "RR", "FL", "FR")
# Indices in car layout reading order: FL FR / RL RR.
CAR_LAYOUT = (2, 3, 0, 1)


@dataclass(frozen=True)
class Channel:
    key: str  # canonical stem; per-wheel channels are stored as f"{key}_{i}"
    label: str
    unit: str
    group: str
    per_wheel: bool = False
    aliases: tuple[str, ...] = ()  # other stems the export may use


# Aliases cover the spellings seen in SRT / F1 UDP dumps; extend when a new export shows others.
CHANNELS: tuple[Channel, ...] = (
    Channel("speed", "Speed", "km/h", "Driver"),
    Channel("throttle", "Throttle", "0-1", "Driver"),
    Channel("brake", "Brake", "0-1", "Driver"),
    Channel("steering", "Steering", "-1..1", "Driver"),
    Channel("gear", "Gear", "", "Driver"),
    Channel("rpm", "RPM", "rpm", "Power unit"),
    Channel("fuel", "Fuel", "kg", "Power unit"),
    Channel("ers_store_mj", "ERS store", "MJ", "Power unit"),
    Channel("engine_temp", "Engine temp", "°C", "Power unit", aliases=("engineTemperature", "engine_temperature")),
    Channel("g_lat", "Lateral g", "g", "Chassis"),
    Channel("g_long", "Longitudinal g", "g", "Chassis"),
    Channel("g_vert", "Vertical g", "g", "Chassis", aliases=("gforce_Y", "gForceVertical")),
    Channel("tyre_temp", "Tyre temp (export)", "°C", "Tyres", per_wheel=True),
    Channel(
        "tyre_surface_temp",
        "Tyre surface temp",
        "°C",
        "Tyres",
        per_wheel=True,
        aliases=("tyres_surface_temperature", "tyreSurfaceTemp", "tyre_surface_temperature", "surface_temp"),
    ),
    Channel(
        "tyre_inner_temp",
        "Tyre inner temp",
        "°C",
        "Tyres",
        per_wheel=True,
        # SRT names the UDP inner (carcass) temperature "tyre_tempInternalAir".
        aliases=(
            "tyre_tempInternalAir",
            "tyres_inner_temperature",
            "tyreInnerTemp",
            "tyre_inner_temperature",
            "inner_temp",
            "carcass_temp",
        ),
    ),
    Channel("tyre_damage", "Tyre damage", "0-1", "Tyres", per_wheel=True, aliases=("tyresDamage",)),
    Channel("tyre_blister", "Tyre blistering", "0-1", "Tyres", per_wheel=True, aliases=("tyreBlisters",)),
    Channel("tyres_age", "Tyre age", "laps", "Tyres", aliases=("tyresAgeLaps", "tyre_age")),
    Channel("pit_status", "Pit status", "0/1/2", "Race", aliases=("pitStatus",)),
    Channel("pitLaneTime", "Pit lane time", "s", "Race", aliases=("pit_lane_time",)),
    Channel("pitStopTime", "Pit stop time", "s", "Race", aliases=("pit_stop_time",)),
    Channel("safetyCarStatus", "Safety car", "0-3", "Race", aliases=("safety_car_status",)),
    Channel("lap_time_invalid", "Lap invalidated", "0/1", "Race", aliases=("currentLapInvalid",)),
    Channel("weather", "Weather", "0-5", "Conditions"),
    Channel("track_temp", "Track temp", "°C", "Conditions", aliases=("trackTemperature",)),
    Channel("air_temp", "Air temp", "°C", "Conditions", aliases=("airTemperature",)),
    Channel("tyre_press", "Tyre pressure", "Pa", "Tyres", per_wheel=True, aliases=("tyres_pressure", "tyrePressure")),
    Channel("tyre_wear", "Tyre wear", "0-1", "Tyres", per_wheel=True, aliases=("tyres_wear", "tyreWear")),
    Channel(
        "wheel_slip_ratio",
        "Slip ratio",
        "",
        "Tyres",
        per_wheel=True,
        aliases=("wheelSlipRatio", "wheel_slip"),
    ),
    Channel(
        "wheel_slip_angle",
        "Slip angle",
        "rad",
        "Tyres",
        per_wheel=True,
        aliases=("wheelSlipAngle", "slip_angle"),
    ),
    Channel(
        "brake_temp",
        "Brake temp",
        "°C",
        "Brakes",
        per_wheel=True,
        aliases=("brakes_temperature", "brakeTemp", "brake_temperature", "brakes_temp"),
    ),
    Channel(
        "susp_pos",
        "Suspension position",
        "mm",
        "Suspension",
        per_wheel=True,
        aliases=("suspension_position", "suspensionPosition", "susp_position"),
    ),
    Channel(
        "susp_vel",
        "Suspension velocity",
        "mm/s",
        "Suspension",
        per_wheel=True,
        aliases=("suspension_velocity", "suspensionVelocity", "susp_velocity"),
    ),
    Channel(
        "wheel_speed",
        "Wheel speed",
        "m/s",
        "Suspension",
        per_wheel=True,
        aliases=("wheelSpeed", "wheel_speeds"),
    ),
)

_BY_KEY = {c.key: c for c in CHANNELS}


def channel(key: str) -> Channel | None:
    return _BY_KEY.get(key)


def _wheel_names(stem: str, i: int) -> tuple[str, ...]:
    return (f"{stem}_{i}", f"{stem}{i}", f"{stem}[{i}]")


def wheel_columns(df: pd.DataFrame, key: str) -> list[str] | None:
    """The four per-wheel columns (RL, RR, FL, FR order) for a channel, or None if incomplete."""
    ch = _BY_KEY.get(key)
    stems = (key, *(ch.aliases if ch else ()))
    for stem in stems:
        for variant in range(3):
            cols = [_wheel_names(stem, i)[variant] for i in range(4)]
            if all(c in df.columns for c in cols):
                return cols
    return None


def resolve(df: pd.DataFrame, key: str) -> str | None:
    """Column holding a scalar channel, by canonical name or alias."""
    ch = _BY_KEY.get(key)
    for stem in (key, *(ch.aliases if ch else ())):
        if stem in df.columns:
            return stem
    return None


def primary_tyre_temp(df: pd.DataFrame) -> tuple[str, list[str]] | None:
    """
    Tyre temperature used for operating windows: inner (carcass) when the export has it,
    else surface, else the generic export channel.
    """
    for key in ("tyre_inner_temp", "tyre_surface_temp", "tyre_temp"):
        cols = wheel_columns(df, key)
        if cols:
            return _BY_KEY[key].label, cols
    return None


def surface_tyre_temp(df: pd.DataFrame) -> tuple[str, list[str]] | None:
    """Surface temperature: the dedicated channel, else the export's generic tyre_temp_i (surface in SRT)."""
    for key in ("tyre_surface_temp", "tyre_temp"):
        cols = wheel_columns(df, key)
        if cols:
            return "Tyre surface temp", cols
    return None


def temp_kind(label: str | None) -> str:
    """'inner' for carcass temperatures, else 'surface' (windows differ by ~15 °C)."""
    return "inner" if label and "inner" in label.lower() else "surface"


def inventory(df: pd.DataFrame) -> pd.DataFrame:
    """Registered channels present in the frame, plus numeric columns the registry does not know yet."""
    rows, claimed = [], set()
    for ch in CHANNELS:
        cols = wheel_columns(df, ch.key) if ch.per_wheel else ([c] if (c := resolve(df, ch.key)) else None)
        if not cols:
            continue
        claimed.update(cols)
        rows.append({"Group": ch.group, "Channel": ch.label, "Unit": ch.unit, "Columns": ", ".join(cols)})
    for col in df.columns:
        if col in claimed or not pd.api.types.is_numeric_dtype(df[col]):
            continue
        rows.append({"Group": "Unregistered", "Channel": col, "Unit": "", "Columns": col})
    return pd.DataFrame(rows)

"""Map F1 UDP packets (2026 format) to the SRT export columns the analysis expects.

One place for names, units and quirks, validated channel by channel against SRT exports of the same
sessions (gate U3, Miami FP/Q/Race, 2026-10-10):

* Wheel arrays: UDP is RL, RR, FL, FR; SRT is front-first FL, FR, RL, RR for every per-wheel channel
  (telemetry, damage, motion-ex and garage): ``srt_i = udp[SRT_WHEEL_FROM_UDP[i]]``.
* World frame: SRT (X, Y, Z) = (-X, Z, Y) of the UDP world frame (position and direction vectors).
* ``velocity_*`` in SRT is the car's local frame: X forward, Y right, Z down.
* G-forces: SRT gforce_X = -longitudinal, gforce_Y = lateral, gforce_Z = vertical (UDP int16 / 1000).
* Angular rates and accelerations: SRT (X, Y, Z) = (-X, Z, Y) of UDP MotionEx.
* 0-based race / grid positions, speed trap in m/s, clutch 0-1.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

PSI_TO_PA = 6894.757293168
G_QUANT = 1000.0  # int16 G-forces are milli-g (fit vs SRT: k = 0.99-1.00)
# SRT susp_pos = k * UDP + c per axle (empirical fit vs SRT, corr 0.978)
SUSP_POS_FIT = {"front": (0.00975, 0.0139), "rear": (0.00965, 0.0199)}
SRT_WHEEL_FROM_UDP = (2, 3, 0, 1)  # SRT index i takes UDP index SRT_WHEEL_FROM_UDP[i]
WHEELS_SRT = ("FL", "FR", "RL", "RR")

# UDP m_trackId -> track name as SRT writes it (the library keys sessions by this name; every value
# resolves to a catalog track via normalize_track_name). Ids from the format's track appendix;
# 42 = Madrid (Madring), new in the 2026 Season Pack. Reverse layouts are separate tracks.
TRACKS: dict[int, str] = {
    0: "Melbourne", 1: "Paul Ricard", 2: "Shanghai", 3: "Bahrain", 4: "Catalunya", 5: "Monaco",
    6: "Montreal", 7: "Silverstone", 8: "Hockenheim", 9: "Hungaroring", 10: "Spa", 11: "Monza",
    12: "Singapore", 13: "Suzuka", 14: "Abu Dhabi", 15: "Austin", 16: "Brazil", 17: "Austria",
    18: "Sochi", 19: "Mexico", 20: "Baku", 21: "Bahrain Short", 22: "Silverstone Short", 23: "Austin Short",
    24: "Suzuka Short", 25: "Hanoi", 26: "Zandvoort", 27: "Imola", 28: "Portimao", 29: "Jeddah",
    30: "Miami", 31: "Las Vegas", 32: "Lusail", 39: "Silverstone Reverse", 40: "Austria Reverse",
    41: "Zandvoort Reverse", 42: "Madring",
}

# UDP m_sessionType -> library tag (telemetry.db.SESSION_TYPES)
SESSION_TYPES: dict[int, str] = {
    1: "FP1", 2: "FP2", 3: "FP3", 4: "FP1", 5: "Quali", 6: "Quali", 7: "Quali", 8: "Quali", 9: "Quali",
    10: "Quali", 11: "Quali", 12: "Quali", 13: "Quali", 14: "Quali", 15: "Race", 16: "Race", 17: "Race",
    18: "Test",
}


def track_name(track_id: int) -> str:
    return TRACKS.get(int(track_id), f"Track{int(track_id)}")


def session_type_name(session_type: int) -> str:
    return SESSION_TYPES.get(int(session_type), "")


def _arr(prefix: str, values, scale: float = 1.0) -> dict[str, float]:
    """UDP wheel array (RL, RR, FL, FR) -> SRT columns ``prefix_0..3`` (FL, FR, RL, RR)."""
    return {f"{prefix}_{i}": float(values[SRT_WHEEL_FROM_UDP[i]]) * scale for i in range(4)}


def setup_row(c) -> dict[str, float]:
    """Garage channels from a CarSetups record. Fractions for percentages, radians for angles, Pa for pressure."""
    deg = np.pi / 180.0
    out = {
        "wing_setup_0": float(c["m_frontWing"]),
        "wing_setup_1": float(c["m_rearWing"]),
        "diff_onThrottle_setup": float(c["m_onThrottle"]) / 100.0,
        "diff_offThrottle_setup": float(c["m_offThrottle"]) / 100.0,
        "brake_press_setup": float(c["m_brakePressure"]) / 100.0,
        "brake_bias_setup": float(c["m_brakeBias"]) / 100.0,
        "brake_engine_setup": float(c["m_engineBraking"]) / 100.0,
        "arb_setup_0": float(c["m_frontAntiRollBar"]),
        "arb_setup_1": float(c["m_rearAntiRollBar"]),
        "ballast_setup": float(c["m_ballast"]),
        "fuel_setup": float(c["m_fuelLoad"]),
    }
    fc, rc = float(c["m_frontCamber"]) * deg, float(c["m_rearCamber"]) * deg
    ft, rt = float(c["m_frontToe"]) * deg, float(c["m_rearToe"]) * deg
    fs, rs = float(c["m_frontSuspension"]), float(c["m_rearSuspension"])
    fh, rh = float(c["m_frontSuspensionHeight"]), float(c["m_rearSuspensionHeight"])
    for i, (cam, toe, spr, hgt) in enumerate(((fc, ft, fs, fh), (fc, ft, fs, fh), (rc, rt, rs, rh), (rc, rt, rs, rh))):
        out[f"camber_setup_{i}"] = cam
        out[f"toe_setup_{i}"] = toe
        out[f"susp_spring_setup_{i}"] = spr
        out[f"susp_height_setup_{i}"] = hgt
    out["tyre_press_setup_0"] = float(c["m_frontLeftTyrePressure"]) * PSI_TO_PA
    out["tyre_press_setup_1"] = float(c["m_frontRightTyrePressure"]) * PSI_TO_PA
    out["tyre_press_setup_2"] = float(c["m_rearLeftTyrePressure"]) * PSI_TO_PA
    out["tyre_press_setup_3"] = float(c["m_rearRightTyrePressure"]) * PSI_TO_PA
    out["front_brake_bias"] = out["brake_bias_setup"]
    return out


def telemetry_row(c) -> dict[str, float]:
    """CarTelemetry record -> SRT channels."""
    out = {
        "throttle": float(c["m_throttle"]),
        "brake": float(c["m_brake"]),
        "clutch": float(c["m_clutch"]) / 100.0,
        "steering": float(c["m_steer"]),
        "gear": int(c["m_gear"]),
        "rpm": float(c["m_engineRPM"]),
        "rev_lights_pct": float(c["m_revLightsPercent"]),
        "drs": int(c["m_drs"]),
        "engine_temp": float(c["m_engineTemperature"]),
    }
    out.update(_arr("brake_temp", c["m_brakesTemperature"]))
    out.update(_arr("tyre_temp", c["m_tyresSurfaceTemperature"]))
    out.update(_arr("tyre_tempInternalAir", c["m_tyresInnerTemperature"]))
    out.update(_arr("tyre_press", c["m_tyresPressure"], PSI_TO_PA))
    out.update(_arr("terrain", c["m_surfaceType"]))
    return out


def status_row(c) -> dict[str, float]:
    """CarStatus record -> SRT channels."""
    out = {
        "fuel": float(c["m_fuelInTank"]),
        "fuel_remainingLaps": float(c["m_fuelRemainingLaps"]),
        "fuel_type": int(c["m_fuelMix"]),
        "front_brake_bias": float(c["m_frontBrakeBias"]) / 100.0,
        "pit_limiter": int(c["m_pitLimiterStatus"]),
        "drs_allowed": int(c["m_drsAllowed"]),
        "drs_distance": float(c["m_drsActivationDistance"]),
        "tyres_age": int(c["m_tyresAgeLaps"]),
        "ice_power": float(c["m_enginePowerICE"]),
        "mguk_power": float(c["m_enginePowerMGUK"]),
        "ers_store": float(c["m_ersStoreEnergy"]),
        "ers_deployMode": int(c["m_ersDeployMode"]),
        "ers_harv_mguk": float(c["m_ersHarvestedThisLapMGUK"]),
        "ers_harv_mguh": float(c["m_ersHarvestedThisLapMGUH"]),
        "ers_harv_limit": float(c["m_ersHarvestLimitPerLap"]),
        "ers_deployed": float(c["m_ersDeployedThisLap"]),
        "flags_status": int(c["m_vehicleFiaFlags"]),
        "traction_ctrl_setup": int(c["m_tractionControl"]),
        "abs_setup": int(c["m_antiLockBrakes"]),
    }
    comp = int(c["m_actualTyreCompound"])
    for i in range(4):
        out[f"tyre_compound_{i}"] = comp
    return out


DAMAGE_PARTS = (
    ("m_frontLeftWingDamage", "front_left_wing_damage"), ("m_frontRightWingDamage", "front_right_wing_damage"),
    ("m_rearWingDamage", "rear_wing_damage"), ("m_floorDamage", "floor_damage"),
    ("m_diffuserDamage", "diffuser_damage"), ("m_sidepodDamage", "sidepod_damage"),
    ("m_drsFault", "drs_damage"), ("m_ersFault", "ers_damage"), ("m_gearBoxDamage", "gear_box_damage"),
    ("m_engineDamage", "engine_damage"), ("m_engineMGUHWear", "mguh_damage"),
    ("m_engineESWear", "es_damage"), ("m_engineCEWear", "ce_damage"),
    ("m_engineICEWear", "ice_damage"), ("m_engineMGUKWear", "mguk_damage"),
    ("m_engineTCWear", "tc_damage"),
)


def damage_row(c) -> dict[str, float]:
    """CarDamage record -> SRT channels (percentages become 0-1 fractions)."""
    out: dict[str, float] = {}
    out.update(_arr("tyre_wear", c["m_tyresWear"], 0.01))
    out.update(_arr("tyre_damage", c["m_tyresDamage"], 0.01))
    out.update(_arr("tyre_blister", c["m_tyreBlisters"], 0.01))
    out.update(_arr("brake_damage", c["m_brakesDamage"], 0.01))
    for src, dst in DAMAGE_PARTS:
        out[dst] = float(c[src]) * 0.01
    out["engine_blown"] = int(c["m_engineBlown"])
    out["engine_seized"] = int(c["m_engineSeized"])
    return out


def _g(raw) -> float:
    """Quantised G-force; the int16 limits are saturation, not data."""
    return float("nan") if int(raw) in (-32768, 32767) else float(raw) / G_QUANT


def motion_row(c) -> dict[str, float]:
    """CarMotion record -> SRT channels (world frame remapped, G-forces as SRT axes)."""
    nrm = 32767.0
    return {
        "world_position_X": -float(c["m_worldPositionX"]), "world_position_Y": float(c["m_worldPositionZ"]),
        "world_position_Z": float(c["m_worldPositionY"]),
        "world_forward_X": -float(c["m_worldForwardDirX"]) / nrm, "world_forward_Y": float(c["m_worldForwardDirZ"]) / nrm,
        "world_forward_Z": float(c["m_worldForwardDirY"]) / nrm,
        "world_right_X": -float(c["m_worldRightDirX"]) / nrm, "world_right_Y": float(c["m_worldRightDirZ"]) / nrm,
        "world_right_Z": float(c["m_worldRightDirY"]) / nrm,
        "gforce_X": -_g(c["m_gForceLongitudinal"]), "gforce_Y": _g(c["m_gForceLateral"]),
        "gforce_Z": _g(c["m_gForceVertical"]),
        "yaw": float(c["m_yaw"]), "pitch": float(c["m_pitch"]), "roll": float(c["m_roll"]),
    }


def motion_ex_row(c) -> dict[str, float]:
    """CarMotionEX record -> SRT channels."""
    out: dict[str, float] = {}
    pos = c["m_suspensionPosition"]
    for i in range(4):
        k, c0 = SUSP_POS_FIT["front" if i < 2 else "rear"]
        out[f"susp_pos_{i}"] = k * float(pos[SRT_WHEEL_FROM_UDP[i]]) + c0
    out.update(_arr("susp_vel", c["m_suspensionVelocity"]))
    out.update(_arr("susp_acc", c["m_suspensionAcceleration"]))
    out.update(_arr("wheel_speed", c["m_wheelSpeed"]))
    out.update(_arr("wheel_slip_ratio", c["m_wheelSlipRatio"]))
    out.update(_arr("wheel_slip_angle", c["m_wheelSlipAngle"]))
    out.update(_arr("wheel_lat_force", c["m_wheelLatForce"]))
    out.update(_arr("wheel_long_force", c["m_wheelLongForce"]))
    out.update(_arr("wheel_vert_force", c["m_wheelVertForce"]))
    out.update(_arr("wheel_camber", c["m_wheelCamber"]))
    out.update(_arr("wheel_camber_gain", c["m_wheelCamberGain"]))
    out["susp_roll_0"] = float(c["m_frontRollAngle"])
    out["susp_roll_1"] = float(c["m_rearRollAngle"])
    out["aero_height_0"] = float(c["m_frontAeroHeight"])
    out["aero_height_1"] = float(c["m_rearAeroHeight"])
    out["cog_height"] = float(c["m_heightOfCOGAboveGround"])
    # UDP local frame: X = left, Y = up, Z = forward -> SRT local frame: X forward, Y right, Z down
    out["velocity_X"] = float(c["m_localVelocityZ"])
    out["velocity_Y"] = -float(c["m_localVelocityX"])
    out["velocity_Z"] = -float(c["m_localVelocityY"])
    for kind, dst in (("Velocity", "angular_vel"), ("Acceleration", "angular_acc")):
        out[f"{dst}_X"] = -float(c[f"m_angular{kind}X"])
        out[f"{dst}_Y"] = float(c[f"m_angular{kind}Z"])
        out[f"{dst}_Z"] = float(c[f"m_angular{kind}Y"])
    out["chassis_yaw"] = float(c["m_chassisYaw"])
    out["chassis_pitch"] = float(c["m_chassisPitch"])
    return out


def telemetry2_row(c) -> dict[str, float]:
    """CarTelemetry2 (2026 active aero / overtake) -> SRT channels."""
    return {
        "activeAero_mode": int(c["m_activeAeroMode"]), "activeAero_allowed": int(c["m_activeAeroAvailable"]),
        "activeAero_distance": float(c["m_activeAeroActivationDistance"]),
        "overtake_allowed": int(c["m_overtakeAvailable"]), "overtake": int(c["m_overtakeActive"]),
        "overtake_distance": float(c["m_overtakeActivationDistance"]),
        "regulations_2026": int(c["m_2026Regulations"]), "driving_wrong_way": int(c["m_drivingWrongWay"]),
    }


def lap_row(c) -> dict[str, float]:
    """LapData record -> SRT channels (lap/bin handled by the recorder)."""
    trap_lap = int(c["m_speedTrapFastestLap"])
    return {
        "pit_status": int(c["m_pitStatus"]),
        "race_position": int(c["m_carPosition"]) - 1,  # SRT is 0-based
        "penalties": int(c["m_penalties"]),
        "warnings": int(c["m_totalWarnings"]),
        "corner_cut_warnings": int(c["m_cornerCuttingWarnings"]),
        "startGridPosition": int(c["m_gridPosition"]) - 1,  # 0-based, -1 = none
        "pitLaneTime": float(c["m_pitLaneTimeInLaneInMS"]) / 1000.0,
        "pitStopTime": float(c["m_pitStopTimerInMS"]) / 1000.0,
        "speedTrapMax": float(c["m_speedTrapFastestSpeed"]) / 3.6,  # m/s
        "speedTrapLap": -1 if trap_lap in (0, 255) else trap_lap - 1,  # SRT: 0-based lap, -1 = none
        "safetyCarDelta": float(c["m_safetyCarDelta"]),
        "delta_front": (int(c["m_deltaToCarInFrontInMinutesPart"]) * 60000 + int(c["m_deltaToCarInFrontInMSPart"])) / 1000.0,
        "delta_leader": (int(c["m_deltaToRaceLeaderInMinutesPart"]) * 60000 + int(c["m_deltaToRaceLeaderInMSPart"])) / 1000.0,
    }


def session_row(b) -> dict[str, float]:
    """Session packet body -> SRT channels."""
    return {
        "weather": int(b["m_weather"]), "track_temp": int(b["m_trackTemperature"]), "air_temp": int(b["m_airTemperature"]),
        "pitSpeedLimit": float(b["m_pitSpeedLimit"]) / 3.6,
        "safetyCarStatus": int(b["m_safetyCarStatus"]), "networkGame": int(b["m_networkGame"]),
        "pitIdealLap": int(b["m_pitStopWindowIdealLap"]) if int(b["m_pitStopWindowIdealLap"]) else -1,
        "pitLatestLap": int(b["m_pitStopWindowLatestLap"]) if int(b["m_pitStopWindowLatestLap"]) else -1,
        "pitRejoinPos": int(b["m_pitStopRejoinPosition"]) if int(b["m_pitStopRejoinPosition"]) else -1,
        "gameMode": int(b["m_gameMode"]), "ruleSet": int(b["m_ruleSet"]), "timeOfDay": int(b["m_timeOfDay"]),
        "sessionLength": int(b["m_sessionLength"]),
        "num_sc": int(b["m_numSafetyCarPeriods"]), "num_vsc": int(b["m_numVirtualSafetyCarPeriods"]),
        "num_red": int(b["m_numRedFlagPeriods"]),
        "steeringAssist": int(b["m_steeringAssist"]), "brakeAssist": int(b["m_brakingAssist"]),
        "gearAssist": int(b["m_gearboxAssist"]), "pitAssist": int(b["m_pitAssist"]),
        "pitReleaseAssist": int(b["m_pitReleaseAssist"]), "ersAssist": int(b["m_ERSAssist"]),
        "drsAssist": int(b["m_DRSAssist"]), "racingLineAssist": int(b["m_dynamicRacingLine"]),
        "racingLineTypeAssist": int(b["m_dynamicRacingLineType"]),
        "absAssist": int(b["m_antiLockBrakesAssist"]), "tractionCtrlAssist": int(b["m_tractionControlAssist"]),
    }


# --------------------------------------------------------------------------- legacy recordings

_WHEEL_PREFIXES = (
    "brake_temp", "tyre_temp", "tyre_tempInternalAir", "tyre_press", "terrain", "tyre_wear", "tyre_damage",
    "tyre_blister", "brake_damage", "susp_pos", "susp_vel", "susp_acc", "wheel_speed", "wheel_slip_ratio",
    "wheel_slip_angle", "wheel_lat_force", "wheel_long_force", "wheel_vert_force", "wheel_camber", "wheel_camber_gain",
)


def legacy_live_to_srt(df: pd.DataFrame) -> pd.DataFrame:
    """Convert a frame recorded before the U3 fixes (UDP wheel order and axes) to the SRT convention.

    The old recordings stored world velocity; it is rotated into the local frame with the stored
    direction vectors (same result as MotionEx local velocity within interpolation error).
    """
    src = df
    cols: dict[str, np.ndarray] = {}
    for pre in _WHEEL_PREFIXES:
        names = [f"{pre}_{i}" for i in range(4)]
        if all(n in src.columns for n in names):
            for i in range(4):
                vals = src[f"{pre}_{SRT_WHEEL_FROM_UDP[i]}"].to_numpy(float)
                if pre == "susp_pos":
                    k, c0 = SUSP_POS_FIT["front" if i < 2 else "rear"]
                    vals = k * vals + c0
                cols[names[i]] = vals
    vel = [f"velocity_{a}" for a in "XYZ"]
    fwd = [f"world_forward_{a}" for a in "XYZ"]
    rgt = [f"world_right_{a}" for a in "XYZ"]
    if all(c in src.columns for c in vel + fwd + rgt):
        v, f, r = (src[x].to_numpy(float) for x in (vel, fwd, rgt))
        up = np.cross(r, f)
        cols["velocity_X"] = (v * f).sum(1)
        cols["velocity_Y"] = (v * r).sum(1)
        cols["velocity_Z"] = -(v * up).sum(1)
    for pre in ("world_position", "world_forward", "world_right"):
        x, y, z = (f"{pre}_{a}" for a in "XYZ")
        if all(c in src.columns for c in (x, y, z)):
            cols[x], cols[y], cols[z] = -src[x].to_numpy(float), src[z].to_numpy(float), src[y].to_numpy(float)
    if all(f"gforce_{a}" in src.columns for a in "XYZ"):  # legacy: X lateral, Y vertical, Z longitudinal
        cols["gforce_X"] = -src["gforce_Z"].to_numpy(float)
        cols["gforce_Y"] = src["gforce_X"].to_numpy(float)
        cols["gforce_Z"] = src["gforce_Y"].to_numpy(float)
    for pre in ("angular_vel", "angular_acc"):
        if all(f"{pre}_{a}" in src.columns for a in "XYZ"):
            cols[f"{pre}_X"] = -src[f"{pre}_X"].to_numpy(float)
            cols[f"{pre}_Y"] = src[f"{pre}_Z"].to_numpy(float)
            cols[f"{pre}_Z"] = src[f"{pre}_Y"].to_numpy(float)
    if "clutch" in src.columns and float(src["clutch"].max()) > 1.5:
        cols["clutch"] = src["clutch"].to_numpy(float) / 100.0
    if "race_position" in src.columns:
        cols["race_position"] = src["race_position"].to_numpy(float) - 1
    if "startGridPosition" in src.columns:
        cols["startGridPosition"] = src["startGridPosition"].to_numpy(float) - 1
    if "speedTrapMax" in src.columns:
        cols["speedTrapMax"] = src["speedTrapMax"].to_numpy(float) / 3.6
    if "speedTrapLap" in src.columns:
        lapcol = src["speedTrapLap"].astype(float)
        cols["speedTrapLap"] = (lapcol - 1).where(~lapcol.isin([0, 255]), -1).to_numpy(float)
    out = src.drop(columns=[c for c in ("rpm_perc",) if c in src.columns]).copy()
    for name, vals in cols.items():
        out[name] = vals
    return out

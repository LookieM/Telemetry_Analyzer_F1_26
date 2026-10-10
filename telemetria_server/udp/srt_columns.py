"""Map F1 UDP packets (2026 format) to the SRT export columns the analysis expects.

One place for names, units and quirks. Wheel arrays are RL, RR, FL, FR in both UDP and SRT telemetry;
SRT garage arrays (``*_setup_i``) are front-first (FL, FR, RL, RR), see ``setup_row``.
"""

from __future__ import annotations

import numpy as np

PSI_TO_PA = 6894.757293168
G_QUANT = 1000.0  # int16 G-forces: ~milli-g (checked against dv/dt and yaw-rate*v on a real capture, +-15%); confirm at gate U3

TRACKS: dict[int, str] = {
    0: "Melbourne", 1: "Paul Ricard", 2: "Shanghai", 3: "Bahrain", 4: "Catalunya", 5: "Monaco",
    6: "Montreal", 7: "Silverstone", 8: "Hockenheim", 9: "Hungaroring", 10: "Spa", 11: "Monza",
    12: "Singapore", 13: "Suzuka", 14: "Abu Dhabi", 15: "Austin", 16: "Brazil", 17: "Austria",
    18: "Sochi", 19: "Mexico", 20: "Baku", 21: "Bahrain", 22: "Silverstone", 23: "Austin",
    24: "Suzuka", 25: "Hanoi", 26: "Zandvoort", 27: "Imola", 28: "Portimao", 29: "Jeddah",
    30: "Miami", 31: "Las Vegas", 32: "Lusail", 39: "Silverstone", 40: "Austria", 41: "Zandvoort",
}

# UDP m_sessionType -> library tag (telemetry.db.SESSION_TYPES)
SESSION_TYPES: dict[int, str] = {
    1: "FP1", 2: "FP2", 3: "FP3", 4: "FP1", 5: "Quali", 6: "Quali", 7: "Quali", 8: "Quali", 9: "Quali",
    10: "Quali", 11: "Quali", 12: "Quali", 13: "Quali", 14: "Quali", 15: "Race", 16: "Race", 17: "Race",
    18: "Test",
}

WHEEL = ("0", "1", "2", "3")  # RL, RR, FL, FR


def track_name(track_id: int) -> str:
    return TRACKS.get(int(track_id), f"Track{int(track_id)}")


def session_type_name(session_type: int) -> str:
    return SESSION_TYPES.get(int(session_type), "")


def _arr(prefix: str, values, scale: float = 1.0) -> dict[str, float]:
    return {f"{prefix}_{i}": float(values[i]) * scale for i in range(4)}


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
        "clutch": float(c["m_clutch"]),
        "steering": float(c["m_steer"]),
        "gear": int(c["m_gear"]),
        "rpm": float(c["m_engineRPM"]),
        "rpm_perc": float(c["m_revLightsPercent"]) / 100.0,
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
    }
    comp = int(c["m_actualTyreCompound"])
    for i in range(4):
        out[f"tyre_compound_{i}"] = comp
    return out


def damage_row(c) -> dict[str, float]:
    """CarDamage record -> SRT channels (percentages become 0-1 fractions)."""
    out: dict[str, float] = {}
    out.update(_arr("tyre_wear", c["m_tyresWear"], 0.01))
    out.update(_arr("tyre_damage", c["m_tyresDamage"], 0.01))
    out.update(_arr("tyre_blister", c["m_tyreBlisters"], 0.01))
    out.update(_arr("brake_damage", c["m_brakesDamage"], 0.01))
    for src, dst in (("m_frontLeftWingDamage", "front_left_wing_damage"), ("m_frontRightWingDamage", "front_right_wing_damage"),
                     ("m_rearWingDamage", "rear_wing_damage"), ("m_floorDamage", "floor_damage"),
                     ("m_diffuserDamage", "diffuser_damage"), ("m_sidepodDamage", "sidepod_damage"),
                     ("m_drsFault", "drs_damage"), ("m_ersFault", "ers_damage"), ("m_gearBoxDamage", "gear_box_damage"),
                     ("m_engineDamage", "engine_damage"), ("m_engineMGUHWear", "mguh_damage"),
                     ("m_engineESWear", "es_damage"), ("m_engineCEWear", "ce_damage"),
                     ("m_engineICEWear", "ice_damage"), ("m_engineMGUKWear", "mguk_damage"),
                     ("m_engineTCWear", "tc_damage")):
        out[dst] = float(c[src]) * 0.01
    out["engine_blown"] = int(c["m_engineBlown"])
    out["engine_seized"] = int(c["m_engineSeized"])
    return out


def _g(raw) -> float:
    """Quantised G-force; the int16 limits are saturation, not data."""
    return float("nan") if int(raw) in (-32768, 32767) else float(raw) / G_QUANT


def motion_row(c) -> dict[str, float]:
    """CarMotion record -> SRT channels."""
    nrm = 32767.0
    return {
        "world_position_X": float(c["m_worldPositionX"]), "world_position_Y": float(c["m_worldPositionY"]),
        "world_position_Z": float(c["m_worldPositionZ"]),
        "velocity_X": float(c["m_worldVelocityX"]), "velocity_Y": float(c["m_worldVelocityY"]),
        "velocity_Z": float(c["m_worldVelocityZ"]),
        "world_forward_X": float(c["m_worldForwardDirX"]) / nrm, "world_forward_Y": float(c["m_worldForwardDirY"]) / nrm,
        "world_forward_Z": float(c["m_worldForwardDirZ"]) / nrm,
        "world_right_X": float(c["m_worldRightDirX"]) / nrm, "world_right_Y": float(c["m_worldRightDirY"]) / nrm,
        "world_right_Z": float(c["m_worldRightDirZ"]) / nrm,
        "gforce_X": _g(c["m_gForceLateral"]), "gforce_Y": _g(c["m_gForceVertical"]),
        "gforce_Z": _g(c["m_gForceLongitudinal"]),
        "yaw": float(c["m_yaw"]), "pitch": float(c["m_pitch"]), "roll": float(c["m_roll"]),
    }


def motion_ex_row(c) -> dict[str, float]:
    """CarMotionEX record -> SRT channels."""
    out: dict[str, float] = {}
    out.update(_arr("susp_pos", c["m_suspensionPosition"]))
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
    for ax in "XYZ":
        out[f"angular_vel_{ax}"] = float(c[f"m_angularVelocity{ax}"])
        out[f"angular_acc_{ax}"] = float(c[f"m_angularAcceleration{ax}"])
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
    return {
        "pit_status": int(c["m_pitStatus"]),
        "race_position": int(c["m_carPosition"]),
        "penalties": int(c["m_penalties"]),
        "warnings": int(c["m_totalWarnings"]),
        "corner_cut_warnings": int(c["m_cornerCuttingWarnings"]),
        "startGridPosition": int(c["m_gridPosition"]),
        "pitLaneTime": float(c["m_pitLaneTimeInLaneInMS"]) / 1000.0,
        "pitStopTime": float(c["m_pitStopTimerInMS"]) / 1000.0,
        "speedTrapMax": float(c["m_speedTrapFastestSpeed"]),
        "speedTrapLap": int(c["m_speedTrapFastestLap"]),
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
    }

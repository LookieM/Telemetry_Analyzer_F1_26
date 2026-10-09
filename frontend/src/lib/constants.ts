export const SESSION_TYPES = ["Race", "Quali", "FP1", "FP2", "FP3", "Test"] as const
export const TRACK_STATES = ["dry", "damp", "inter", "wet"] as const
export const TYRE_STATE_LABEL: Record<string, string> = { dry: "Dry", damp: "Damp", inter: "Intermediate", wet: "Wet" }

import { describe, expect, it } from "vitest"
import type { CoachItem } from "../api/types"
import { groupByDomain, titleCase } from "./coach"

const item = (id: string, domain: string, score: number): CoachItem => ({
  id,
  source: "corner",
  domain,
  action_kind: "drive",
  severity: "tip",
  priority: score,
  confidence: 1,
  score,
  title: id,
  detail: "",
  related_keys: [],
})

describe("groupByDomain", () => {
  it("groups alphabetically, best score first inside a group", () => {
    const groups = groupByDomain([item("a", "tyres", 1), item("b", "energy", 2), item("c", "tyres", 3)])
    expect(groups.map((g) => g.domain)).toEqual(["energy", "tyres"])
    expect(groups[1].items.map((i) => i.id)).toEqual(["c", "a"])
  })
  it("handles an empty feed", () => {
    expect(groupByDomain([])).toEqual([])
  })
})

describe("titleCase", () => {
  it("capitalises the first letter", () => {
    expect(titleCase("understeer")).toBe("Understeer")
    expect(titleCase("")).toBe("")
  })
})

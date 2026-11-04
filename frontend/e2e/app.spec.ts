import { expect, test, type Page } from "@playwright/test"

interface SessionRow {
  id: number
  source_name: string
}

let austriaId = 0

test.beforeAll(async ({ request }) => {
  const sessions = (await (await request.get("/api/sessions")).json()) as SessionRow[]
  austriaId = sessions.find((s) => s.source_name === "Austria_race.csv")!.id
})

/** Collect console errors, page errors and failed API calls while `fn` runs. */
async function withErrorWatch(page: Page, fn: () => Promise<void>): Promise<string[]> {
  const errors: string[] = []
  page.on("console", (m) => m.type() === "error" && errors.push(`console: ${m.text()}`))
  page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`))
  page.on("response", (r) => r.url().includes("/api/") && r.status() >= 400 && errors.push(`http ${r.status()}: ${r.url()}`))
  await fn()
  return errors
}

/** A point on the drawn racing line (CSS px relative to the canvas), found from the canvas pixels. */
async function pointOnLine(page: Page, fraction: number): Promise<{ x: number; y: number }> {
  const canvas = page.getByTestId("track-map-canvas")
  await expect(canvas).toHaveAttribute("data-ready", /\d+/)
  const pts = await canvas.evaluate((el: HTMLCanvasElement) => {
    const ctx = el.getContext("2d")!
    const { width, height } = el
    const data = ctx.getImageData(0, 0, width, height).data
    const out: [number, number][] = []
    for (let y = 0; y < height; y += 3) {
      for (let x = 0; x < width; x += 3) {
        const i = (y * width + x) * 4
        if (data[i + 3] > 240 && data[i] + data[i + 1] + data[i + 2] > 60) out.push([x * (el.clientWidth / width), y * (el.clientHeight / height)])
      }
    }
    return out
  })
  expect(pts.length).toBeGreaterThan(100)
  const [x, y] = pts[Math.floor(pts.length * fraction)]
  return { x, y }
}

const legendValue = (page: Page) => page.getByTestId("driver-trace").locator(".u-legend").first().locator(".u-series").nth(1).locator(".u-value")

test("library lists the sessions and opens one", async ({ page }) => {
  const errors = await withErrorWatch(page, async () => {
    await page.goto("/")
    await expect(page.getByTestId("sessions-table")).toBeVisible()
    await expect(page.getByTestId("sessions-table").locator("tbody tr").first()).toBeVisible()
    expect(await page.getByTestId("sessions-table").locator("tbody tr").count()).toBeGreaterThan(5)
    await expect(page.getByRole("row", { name: /Austria_race\.csv/ })).toBeVisible()
    // filters
    await page.getByLabel("Filter track").selectOption("Austria")
    const rows = page.getByTestId("sessions-table").locator("tbody tr")
    await expect(rows.first()).toContainText("Austria")
    for (const text of await rows.allTextContents()) expect(text).toContain("Austria")
    await page.getByRole("row", { name: /Austria_race\.csv/ }).click()
    await expect(page).toHaveURL(new RegExp(`/session/${austriaId}/laps`))
    await expect(page.getByTestId("session-title")).toContainText("Austria")
  })
  expect(errors).toEqual([])
})

test("laps: hovering the map moves the trace legend and hovering a trace moves the map", async ({ page }) => {
  const errors = await withErrorWatch(page, async () => {
    await page.goto(`/session/${austriaId}/laps`)
    await expect(page.getByTestId("driver-trace").locator("canvas").first()).toBeVisible()
    await expect(page.getByTestId("track-map-canvas")).toBeVisible()
    const canvas = page.getByTestId("track-map-canvas")

    const before = (await legendValue(page).innerText()).trim()
    const box = (await canvas.boundingBox())!
    const a = await pointOnLine(page, 0.25)
    await page.mouse.move(box.x + a.x, box.y + a.y)
    await expect(page.getByTestId("map-readout")).toContainText(" m")
    await expect(legendValue(page)).not.toHaveText(before)
    const atA = (await legendValue(page).innerText()).trim()
    expect(atA).toMatch(/^\d+$/) // speed with 0 decimals

    const b = await pointOnLine(page, 0.7)
    await page.mouse.move(box.x + b.x, box.y + b.y, { steps: 4 })
    await expect(legendValue(page)).not.toHaveText(atA)
    // and the map readout speed matches the legend speed
    const mapSpeed = (await page.locator('[data-testid="map-readout"] [data-channel="Speed"]').innerText()).trim()
    expect(mapSpeed).toBe((await legendValue(page).innerText()).trim())

    // the other direction: hover the trace -> map readout head (distance) follows
    await page.mouse.move(box.x + 5, box.y + box.height + 40) // leave the map
    const over = page.getByTestId("driver-trace").locator(".u-over").first()
    const ob = (await over.boundingBox())!
    await page.mouse.move(ob.x + ob.width * 0.2, ob.y + ob.height / 2)
    const head = page.getByTestId("map-readout").locator(".tm-head")
    await expect(head).toContainText(" m")
    const d1 = (await head.innerText()).trim()
    await page.mouse.move(ob.x + ob.width * 0.8, ob.y + ob.height / 2, { steps: 4 })
    await expect(head).not.toHaveText(d1)

    // click pins the cursor on both
    await page.mouse.click(ob.x + ob.width * 0.5, ob.y + ob.height / 2)
    await page.mouse.move(box.x + 5, box.y + box.height + 60)
    await expect(page.getByTestId("metric-cursor")).toContainText("pinned")
  })
  expect(errors).toEqual([])
})

test("laps: compare to another lap shows deltas and sector tables", async ({ page }) => {
  const errors = await withErrorWatch(page, async () => {
    await page.goto(`/session/${austriaId}/laps`)
    await page.getByLabel("Reference type").selectOption("lap")
    await page.getByLabel("Reference lap").selectOption({ index: 5 })
    await expect(page.getByTestId("sector-table").locator("tbody tr")).toHaveCount(3)
    await expect(page.getByTestId("mini-sector-table").locator("tbody tr")).toHaveCount(12)
    await expect(page.getByTestId("metric-delta")).toBeVisible()
    await page.getByLabel("Map colour").selectOption("delta")
    await expect(page.getByTestId("track-map").locator(".tm-legend")).toContainText("Δt")
  })
  expect(errors).toEqual([])
})

test("laps: compare against another session", async ({ page }) => {
  const errors = await withErrorWatch(page, async () => {
    await page.goto(`/session/${austriaId}/laps`)
    await page.getByLabel("Reference type").selectOption("session")
    await expect(page.getByLabel("Reference session")).toBeVisible()
    await expect(page.getByTestId("metric-delta")).toBeVisible()
    await expect(page.getByTestId("sector-table").locator("tbody tr")).toHaveCount(3)
  })
  expect(errors).toEqual([])
})

test("laps: session pace chart and the G-G diagram follow the lap cursor", async ({ page }) => {
  const errors = await withErrorWatch(page, async () => {
    await page.goto(`/session/${austriaId}/laps`)
    await expect(page.getByTestId("session-pace-chart").locator("canvas").first()).toBeVisible()
    const gg = page.getByTestId("gg-diagram")
    await expect(gg.locator("circle").nth(50)).toBeAttached()
    await expect(gg.locator(".gg-cursor")).toHaveCount(0)
    const over = page.getByTestId("driver-trace").locator(".u-over").first()
    const ob = (await over.boundingBox())!
    await page.mouse.move(ob.x + ob.width * 0.4, ob.y + ob.height / 2)
    await expect(gg.locator(".gg-cursor")).toHaveCount(1)
    await expect(gg).toContainText(" g")
  })
  expect(errors).toEqual([])
})

test("session details: track state select shows the weather banner", async ({ page }) => {
  const errors = await withErrorWatch(page, async () => {
    await page.goto(`/session/${austriaId}/laps`)
    await page.getByRole("button", { name: "Details" }).click()
    await page.getByLabel("Track state").selectOption("inter")
    await page.getByRole("button", { name: /Save tags/ }).click()
    await expect(page.getByTestId("weather-banner")).toContainText("Intermediate")
    await page.getByLabel("Track state").selectOption("dry")
    await page.getByRole("button", { name: /Save tags/ }).click()
    await expect(page.getByTestId("weather-banner")).toHaveCount(0)
  })
  expect(errors).toEqual([])
})

test("coach: session read and ranked callouts", async ({ page }) => {
  const errors = await withErrorWatch(page, async () => {
    await page.goto(`/session/${austriaId}/coach`)
    await expect(page.getByTestId("coach-headline")).not.toBeEmpty({ timeout: 45_000 })
    await expect(page.getByTestId("coach-top")).toBeVisible()
    const more = page.getByTestId("coach-more")
    if (await more.count()) {
      const before = await page.getByTestId("coach-callout").count()
      await more.click()
      expect(await page.getByTestId("coach-callout").count()).toBeGreaterThan(before)
    }
  })
  expect(errors).toEqual([])
})

test("tyres: four stints, car grid and model", async ({ page }) => {
  const errors = await withErrorWatch(page, async () => {
    await page.goto(`/session/${austriaId}/tyres`)
    await expect(page.getByTestId("stints-table")).toBeVisible()
    await expect(page.getByTestId("stints-table").locator("tbody tr")).toHaveCount(4)
    await expect(page.getByTestId("stint-timeline").first().getByTestId("stint-segment")).toHaveCount(4)
    await expect(page.getByTestId("car-grid")).toBeVisible()
    await expect(page.getByTestId("car-grid").locator(".cg-card")).toHaveCount(4)
    await expect(page.getByTestId("tyre-lap-trace").locator("canvas").first()).toBeVisible()
    await expect(page.getByTestId("stint-trace").locator("canvas").first()).toBeVisible()
    await expect(page.getByTestId("pressure-table").locator("tbody tr")).toHaveCount(4)
    await expect(page.getByTestId("model-table")).toBeVisible()
  })
  expect(errors).toEqual([])
})

test("strategy: best plan and race review", async ({ page }) => {
  const errors = await withErrorWatch(page, async () => {
    await page.goto(`/session/${austriaId}/strategy`)
    await expect(page.getByTestId("best-plan")).toContainText("-stop")
    await expect(page.getByTestId("best-box")).toContainText("L")
    await expect(page.getByTestId("plans-table").locator("tbody tr").first()).toBeVisible()
    await expect(page.getByTestId("race-trace").locator("canvas").first()).toBeVisible()
    await expect(page.getByTestId("race-review")).toBeVisible()
    await expect(page.getByTestId("review-actual")).toContainText("Actual race")
    await page.getByTestId("panel-calls").click()
    await expect(page.getByTestId("calls-table").locator("tbody tr").first()).toBeVisible()
    await page.getByTestId("panel-sensitivity").click()
    await expect(page.getByTestId("sensitivity-table").locator("tbody tr").first()).toBeVisible()
    // editing the model re-plans
    const before = await page.getByTestId("best-plan").innerText()
    await page.getByLabel("Race laps").fill("20")
    await expect(page.getByTestId("best-plan")).not.toHaveText(before, { timeout: 20_000 })
  })
  expect(errors).toEqual([])
})

test("planner works for any track and deep links survive a reload", async ({ page }) => {
  const errors = await withErrorWatch(page, async () => {
    await page.goto("/planner")
    await expect(page.getByTestId("best-plan")).toContainText("-stop")
    await page.getByLabel("Track", { exact: true }).selectOption("Bahrain")
    await expect(page.getByTestId("model-sources")).toContainText("#2", { timeout: 20_000 }) // the Bahrain race
    await page.reload()
    await expect(page.getByTestId("planner")).toBeVisible()
    await page.goto(`/session/${austriaId}/tyres`)
    await page.reload()
    await expect(page.getByTestId("stints-table")).toBeVisible()
  })
  expect(errors).toEqual([])
})

/**
 * Builds a throw-away library (copy of data/telemetry.db + three parquet files) and starts the real server on it.
 * The real `data/` folder is only ever read by e2e/support/make_library.py (SQLite backup API + file copies).
 */
import { spawn, spawnSync } from "node:child_process"
import fs from "node:fs"
import os from "node:os"
import path from "node:path"
import { fileURLToPath } from "node:url"

const here = path.dirname(fileURLToPath(import.meta.url))
const frontendDir = path.resolve(here, "..")
const repoRoot = path.resolve(frontendDir, "..")
const PORT = 8771
export const STATE_FILE = path.join(frontendDir, "test-results", ".server.json")

function findPython(): string {
  if (process.env.PYTHON) return process.env.PYTHON
  let dir = repoRoot
  for (let i = 0; i < 6; i++) {
    const candidate = path.join(dir, ".venv", "Scripts", "python.exe")
    if (fs.existsSync(candidate)) return candidate
    const posix = path.join(dir, ".venv", "bin", "python")
    if (fs.existsSync(posix)) return posix
    dir = path.dirname(dir)
  }
  return "python"
}

async function waitForHealth(url: string, timeoutMs: number): Promise<void> {
  const start = Date.now()
  while (Date.now() - start < timeoutMs) {
    try {
      const res = await fetch(url)
      if (res.ok) return
    } catch {
      /* not up yet */
    }
    await new Promise((r) => setTimeout(r, 300))
  }
  throw new Error(`Server did not become healthy at ${url}`)
}

export default async function globalSetup(): Promise<void> {
  if (!fs.existsSync(path.join(frontendDir, "dist", "index.html"))) {
    throw new Error("frontend/dist is missing - run `npm run build` first (or `npm run e2e`).")
  }
  const python = findPython()
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "telemetria-e2e-"))
  const make = spawnSync(python, [path.join(here, "support", "make_library.py"), tmp, repoRoot], { encoding: "utf8" })
  if (make.status !== 0) throw new Error(`make_library failed:\n${make.stdout}\n${make.stderr}`)

  const log = fs.openSync(path.join(tmp, "server.log"), "w")
  const server = spawn(python, ["-m", "telemetria_server", "--no-browser", "--port", String(PORT), "--app-root", tmp], {
    cwd: repoRoot,
    stdio: ["ignore", log, log],
    windowsHide: true,
  })
  fs.mkdirSync(path.dirname(STATE_FILE), { recursive: true })
  fs.writeFileSync(STATE_FILE, JSON.stringify({ pid: server.pid, tmp }))
  try {
    await waitForHealth(`http://127.0.0.1:${PORT}/api/health`, 60_000)
  } catch (err) {
    server.kill()
    throw new Error(`${String(err)}\n${fs.readFileSync(path.join(tmp, "server.log"), "utf8")}`)
  }
}

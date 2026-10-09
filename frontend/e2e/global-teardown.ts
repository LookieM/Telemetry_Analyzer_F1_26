import { spawnSync } from "node:child_process"
import fs from "node:fs"
import { STATE_FILE } from "./global-setup"

export default async function globalTeardown(): Promise<void> {
  if (!fs.existsSync(STATE_FILE)) return
  const { pid, tmp } = JSON.parse(fs.readFileSync(STATE_FILE, "utf8")) as { pid: number; tmp: string }
  if (pid) {
    if (process.platform === "win32") spawnSync("taskkill", ["/PID", String(pid), "/T", "/F"])
    else {
      try {
        process.kill(pid)
      } catch {
        /* already gone */
      }
    }
  }
  await new Promise((r) => setTimeout(r, 500))
  if (tmp) fs.rmSync(tmp, { recursive: true, force: true, maxRetries: 5, retryDelay: 300 })
  fs.rmSync(STATE_FILE, { force: true })
}

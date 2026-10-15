/** Thin fetch wrapper: JSON in / out, errors carry the server's `detail`. */
import type { BaselinePayload, BaselineRequest, EngineerAnswer, EngineerView } from "./types"

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message)
  }
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init)
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      if (body?.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail)
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, detail)
  }
  return (await res.json()) as T
}

export function qs(params: Record<string, string | number | boolean | null | undefined>): string {
  const sp = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") sp.set(k, String(v))
  const s = sp.toString()
  return s ? `?${s}` : ""
}

export const api = {
  get: <T>(path: string) => request<T>(`/api${path}`),
  send: <T>(method: "POST" | "PUT" | "PATCH" | "DELETE", path: string, body?: unknown) =>
    request<T>(`/api${path}`, {
      method,
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
  upload: <T>(path: string, form: FormData) => request<T>(`/api${path}`, { method: "POST", body: form }),
}

/** Live race engineer commands; each returns the new engineer view (409 = refused, `detail` is the reason). */
export const engineerApi = {
  start: (program: "short" | "full", minutes?: number) => api.send<EngineerView>("POST", "/live/engineer/start", minutes ? { program, minutes } : { program }),
  answer: (a: EngineerAnswer) => api.send<EngineerView>("POST", "/live/engineer/answer", a),
  confirm: (winner: "1" | "2") => api.send<EngineerView>("POST", "/live/engineer/confirm", { winner }),
  revert: (accept: boolean) => api.send<EngineerView>("POST", "/live/engineer/revert", { accept }),
  skip: () => api.send<EngineerView>("POST", "/live/engineer/skip"),
  nextPhase: () => api.send<EngineerView>("POST", "/live/engineer/next-phase"),
  stop: () => api.send<EngineerView>("POST", "/live/engineer/stop"),
}

export const baselineApi = {
  set: (track: string, body: BaselineRequest) => api.send<BaselinePayload>("POST", `/tracks/${encodeURIComponent(track)}/baseline`, body),
}

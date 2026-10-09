/** Thin fetch wrapper: JSON in / out, errors carry the server's `detail`. */

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

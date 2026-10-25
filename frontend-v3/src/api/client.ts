/** Tiny fetch wrapper: same-origin cookies, JSON in/out, FastAPI `{detail}` errors → ApiError. */

export class ApiError extends Error {
  readonly status: number
  readonly detail: string
  /** Seconds until a lockout or cap lifts, from `Retry-After` when the server sends it. */
  readonly retryAfter: number | null
  /** On 429: "cap" | "rate_limit" | "lockout". */
  readonly kind: string | null

  constructor(status: number, detail: string, retryAfter: number | null = null, kind: string | null = null) {
    super(detail || `Request failed (${status})`)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
    this.retryAfter = retryAfter
    this.kind = kind
  }
}

type Body = Record<string, unknown> | FormData | undefined

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'DELETE'
  body?: Body
  signal?: AbortSignal
}

function detailOf(payload: unknown): string {
  if (!payload || typeof payload !== 'object') return ''
  const d = (payload as { detail?: unknown }).detail
  if (typeof d === 'string') return d
  // FastAPI validation errors: [{loc, msg, type}]
  if (Array.isArray(d)) return d.map((x) => (x && typeof x === 'object' && 'msg' in x ? String(x.msg) : String(x))).join('; ')
  if (d && typeof d === 'object' && 'message' in d) return String((d as { message: unknown }).message)
  return ''
}

export async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, signal } = opts
  const headers: Record<string, string> = { Accept: 'application/json' }
  let payload: BodyInit | undefined
  if (body instanceof FormData) payload = body
  else if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
    payload = JSON.stringify(body)
  }

  let res: Response
  try {
    res = await fetch(path, { method, body: payload, headers, credentials: 'same-origin', signal })
  } catch (err) {
    if ((err as Error).name === 'AbortError') throw err
    throw new ApiError(0, 'Cannot reach the Tea Rose server. Check your connection and try again.')
  }

  const type = res.headers.get('content-type') ?? ''
  const data: unknown = type.includes('application/json')
    ? await res.json().catch(() => null)
    : await res.text().catch(() => '')

  if (!res.ok) {
    const ra = res.headers.get('retry-after')
    const retry = ra && /^\d+$/.test(ra) ? Number(ra) : null
    const detail = detailOf(data) || (typeof data === 'string' && data.length < 300 ? data : '') || res.statusText
    const kind = data && typeof data === 'object' && typeof (data as { kind?: unknown }).kind === 'string' ? (data as { kind: string }).kind : null
    throw new ApiError(res.status, detail, retry, kind)
  }
  return data as T
}

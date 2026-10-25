import { EVENT_TYPES, type AnalysisResult, type SampleRef, type TraceEvent } from '../types'
import { request } from './client'
import type { Api, StreamHandlers } from './contract'

const enc = encodeURIComponent

function normalizeSamples(raw: unknown): SampleRef[] {
  // Contract says "names of sample documents"; accept string[] or [{name,title?}] or {samples:[…]}.
  const list = Array.isArray(raw) ? raw : raw && typeof raw === 'object' && Array.isArray((raw as { samples?: unknown }).samples) ? (raw as { samples: unknown[] }).samples : []
  return list
    .map((x) => (typeof x === 'string' ? { name: x } : x && typeof x === 'object' && 'name' in x ? (x as SampleRef) : null))
    .filter((x): x is SampleRef => x !== null)
}

/**
 * SSE over EventSource (same-origin, so the HttpOnly session cookie is sent).
 * The server replays events with seq > after, then streams live ones and closes when the run
 * ends. We accept both unnamed `data:` messages and messages named after the event type, dedupe
 * by seq, and on a dropped connection reconnect from the last seen seq with backoff. If the run
 * already finished while we were disconnected, we stop instead of reconnecting.
 */
function streamEvents(id: string, after: number, h: StreamHandlers): () => void {
  let lastSeq = after
  let es: EventSource | null = null
  let closed = false
  let attempts = 0
  let timer: ReturnType<typeof setTimeout> | undefined

  const stop = () => {
    closed = true
    clearTimeout(timer)
    es?.close()
    es = null
  }

  const handle = (msg: MessageEvent<string>) => {
    let ev: TraceEvent
    try {
      const parsed = JSON.parse(msg.data) as TraceEvent | { event: TraceEvent }
      ev = 'event' in parsed && parsed.event && typeof parsed.event === 'object' ? parsed.event : (parsed as TraceEvent)
    } catch {
      return
    }
    if (typeof ev.seq === 'number' && ev.seq <= lastSeq) return
    if (typeof ev.seq === 'number') lastSeq = ev.seq
    attempts = 0
    h.onEvent(ev)
    // Only `done` (or a failure) ends the stream; a follow-up may extend a run after run_finished.
    if (ev.type === 'run_failed') {
      stop()
      h.onEnd()
    }
  }

  const open = () => {
    if (closed) return
    es = new EventSource(`/api/analyze/${enc(id)}/events?after=${lastSeq}`, { withCredentials: true })
    es.onopen = () => h.onConnection?.('open')
    es.onmessage = handle
    // Backend sends `event: trace` (id = seq) per TraceEvent, then one `event: done` {status, error}.
    es.addEventListener('trace', handle as EventListener)
    for (const t of EVENT_TYPES) es.addEventListener(t, handle as EventListener)
    es.addEventListener('done', () => {
      stop()
      h.onEnd()
    })
    es.onerror = async () => {
      es?.close()
      es = null
      if (closed) return
      // The server closes the stream when the run ends; check before reconnecting.
      try {
        const r = await request<AnalysisResult>(`/api/analyze/${enc(id)}`)
        if (r.status === 'finished' || r.status === 'failed') {
          stop()
          h.onEnd()
          return
        }
      } catch {
        /* fall through to retry */
      }
      attempts += 1
      if (attempts > 6) {
        stop()
        h.onConnection?.('lost')
        return
      }
      h.onConnection?.('retrying')
      timer = setTimeout(open, Math.min(500 * 2 ** attempts, 8000))
    }
  }

  open()
  return stop
}

export const httpApi: Api = {
  me: () => request('/api/auth/me'),
  limits: () => request('/api/limits'),
  login: async (passcode) => {
    await request('/api/auth/login', { method: 'POST', body: { passcode } })
  },
  logout: async () => {
    await request('/api/auth/logout', { method: 'POST' })
  },
  showcase: () => request('/api/showcase'),
  showcaseCase: (slug) => request(`/api/showcase/${enc(slug)}`),
  samples: async () => normalizeSamples(await request<unknown>('/api/samples')),
  sample: async (name) => {
    const r = await request<unknown>(`/api/samples/${enc(name)}`)
    if (typeof r === 'string') return r
    if (r && typeof r === 'object' && 'text' in r) return String((r as { text: unknown }).text)
    return ''
  },
  analyze: (input) => {
    if ('file' in input) {
      const fd = new FormData()
      fd.append('file', input.file)
      return request('/api/analyze', { method: 'POST', body: fd })
    }
    return request('/api/analyze', { method: 'POST', body: { text: input.text } })
  },
  run: (id) => request(`/api/analyze/${enc(id)}`),
  followup: (id, question) => request(`/api/analyze/${enc(id)}/followup`, { method: 'POST', body: { question } }),
  streamEvents,
}

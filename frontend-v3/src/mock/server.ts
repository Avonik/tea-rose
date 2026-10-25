/**
 * Mock backend for `VITE_MOCK=1`. Implements the same Api as the HTTP layer:
 * - showcase / samples come from JSON files in this folder;
 * - a new analysis replays the Jack Daniel's trace on timers, and GET /analyze/:id returns a
 *   partial result that fills in as each node finishes (like the real backend);
 * - auth is simulated: passcode `tearose` works, `disabled` returns 503, five wrong attempts
 *   lock out (429). State survives reloads via sessionStorage.
 */
import { ApiError } from '../api/client'
import type { Api, StreamHandlers } from '../api/contract'
import type { AnalysisResult, AuthMe, ShowcaseSummary, TraceEvent } from '../types'
import fixture from './jack-daniels.json'
import samples from './samples.json'
import showcaseList from './showcase.json'

const BASE = fixture as unknown as AnalysisResult
const SPEED = 0.16 // replay at ~6 s instead of ~41 s
const KEY = 'tearose-mock'

interface MockRun {
  id: string
  start: number
  followups: { question: string; start: number }[]
}
interface MockState {
  authenticated: boolean
  failures: number
  lockedUntil: number
  runsLeftToday: number
  runsLeftSession: number
  runs: Record<string, MockRun>
}

function load(): MockState {
  try {
    const s = sessionStorage.getItem(KEY)
    if (s) return JSON.parse(s) as MockState
  } catch {
    /* storage unavailable */
  }
  return { authenticated: false, failures: 0, lockedUntil: 0, runsLeftToday: 58, runsLeftSession: 15, runs: {} }
}
let state = load()
function save() {
  try {
    sessionStorage.setItem(KEY, JSON.stringify(state))
  } catch {
    /* ignore */
  }
}

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms + Math.random() * ms * 0.5))
const clone = <T,>(x: T): T => structuredClone(x)

// Offsets (ms after run start) at which each base event becomes visible.
const t0 = Date.parse(BASE.trace[0].ts)
const OFFSETS = BASE.trace.map((e) => Math.max(0, (Date.parse(e.ts) - t0) * SPEED))

function followupEvents(question: string, firstSeq: number, start: number): { ev: TraceEvent; at: number }[] {
  const q = question.length > 70 ? `${question.slice(0, 70)}…` : question
  const items: [number, Omit<TraceEvent, 'seq' | 'ts'>][] = [
    [0, { node: 'followup', type: 'node_started', title: 'Follow-up received', detail: q, data: {} }],
    [700, { node: 'followup', type: 'decision', title: 'Re-enter at resolve; reuse cached evidence', detail: 'Only the affected section is rewritten; scores are recomputed from the same queries.', data: {} }],
    [1300, { node: 'fetch', type: 'tool_call', title: 'Re-check pet-supply ranks (cached)', detail: null, data: { tool: 'qloo_insights_entities', endpoint: '/v2/insights', params: { 'filter.type': 'urn:entity:brand', 'filter.tags': 'urn:tag:category:qloo:pet_supplies', take: 50, page: 1 } } }],
    [1500, { node: 'fetch', type: 'tool_result', title: '50 brands (cache hit)', detail: null, data: { endpoint: '/v2/insights', result_count: 50, cache_hit: true, elapsed_ms: 8 } }],
    [2600, { node: 'memo', type: 'node_finished', title: 'Follow-up section added', detail: null, data: {} }],
    [2700, { node: 'followup', type: 'run_finished', title: 'Answer ready', detail: null, data: {} }],
  ]
  return items.map(([at, e], i) => ({ at: start + at, ev: { ...e, seq: firstSeq + i, ts: new Date(start + at).toISOString() } }))
}

/** All events of a mock run visible at `now`, with fresh timestamps. */
function visible(run: MockRun, now = Date.now()): TraceEvent[] {
  const out: TraceEvent[] = []
  BASE.trace.forEach((e, i) => {
    const at = run.start + OFFSETS[i]
    if (at <= now) out.push({ ...e, ts: new Date(at).toISOString() })
  })
  let seq = BASE.trace.length + 1
  for (const f of run.followups) {
    for (const { ev, at } of followupEvents(f.question, seq, f.start)) if (at <= now) out.push(ev)
    seq += 6
  }
  return out
}

function totalEvents(run: MockRun) {
  return BASE.trace.length + run.followups.length * 6
}

function buildResult(run: MockRun): AnalysisResult {
  const trace = visible(run)
  const finished = (node: string) => trace.some((e) => e.node === node && e.type === 'node_finished')
  const done = trace.length >= totalEvents(run)
  const r = clone(BASE)
  r.run_id = run.id
  r.showcase_slug = null
  r.mode = 'fixture'
  r.created_at = new Date(run.start).toISOString()
  r.status = done ? 'finished' : 'running'
  r.trace = trace
  if (!finished('extract')) r.extraction = null
  if (!finished('route')) r.routing = null
  if (!finished('resolve')) r.resolution = null
  if (!finished('score')) r.evidence = null
  if (!finished('memo')) r.memo = null
  if (r.memo) {
    run.followups.forEach((f, i) => {
      const answered = trace.some((e) => e.seq === BASE.trace.length + i * 6 + 5)
      if (!answered) return
      r.memo!.sections.push({
        id: `followup-${i + 1}`,
        title: `Follow-up: ${f.question}`,
        markdown:
          'Mock answer. In live mode the agent re-enters at **resolve** with this instruction, reruns only the affected queries and rewrites this section. Scores still come from code, and any new query is added to the appendix.',
      })
    })
  }
  return r
}

function requireAuth() {
  if (!state.authenticated) throw new ApiError(401, 'Not authenticated.')
}
function getRun(id: string) {
  const run = state.runs[id]
  if (!run) throw new ApiError(404, `No run with id ${id}.`)
  return run
}

export const mockApi: Api = {
  async me(): Promise<AuthMe> {
    await wait(120)
    return { authenticated: state.authenticated, runs_left_today: state.runsLeftToday, runs_left_session: state.authenticated ? state.runsLeftSession : null }
  },
  async limits() {
    await wait(100)
    return { daily_cap: 60, daily_used: 60 - state.runsLeftToday, session_cap: 15, live_mode_enabled: true }
  },
  async login(passcode) {
    await wait(350)
    const now = Date.now()
    if (state.lockedUntil > now) throw new ApiError(429, 'Too many failed attempts. Try again in 15 minutes.', Math.ceil((state.lockedUntil - now) / 1000), 'lockout')
    if (passcode === 'disabled') throw new ApiError(503, 'Live mode is disabled right now.')
    if (passcode !== 'tearose') {
      state.failures += 1
      if (state.failures >= 5) {
        state.lockedUntil = now + 15 * 60 * 1000
        state.failures = 0
        save()
        throw new ApiError(429, 'Too many failed attempts. Try again in 15 minutes.', 900, 'lockout')
      }
      save()
      throw new ApiError(401, 'Incorrect passcode.')
    }
    state.authenticated = true
    state.failures = 0
    save()
  },
  async logout() {
    await wait(100)
    state.authenticated = false
    save()
  },
  async showcase() {
    await wait(250)
    return showcaseList as ShowcaseSummary[]
  },
  async showcaseCase(slug) {
    await wait(300)
    if (slug !== BASE.showcase_slug) throw new ApiError(404, 'This case is not in the mock dataset. Only "Bad Spaniels" ships with full mock data.')
    return clone(BASE)
  },
  async samples() {
    await wait(150)
    return samples.map(({ name, title, text }) => ({ name, title, bytes: text.length }))
  },
  async sample(name) {
    await wait(150)
    const s = samples.find((x) => x.name === name)
    if (!s) throw new ApiError(404, 'Sample not found.')
    return s.text
  },
  async analyze(input) {
    await wait(400)
    requireAuth()
    if ('text' in input && input.text.trim().length < 40) throw new ApiError(422, 'The document is too short to analyze (40 characters minimum).')
    if (state.runsLeftSession <= 0 || state.runsLeftToday <= 0) throw new ApiError(429, 'The live-analysis cap for this session is reached.', null, 'cap')
    state.runsLeftSession -= 1
    state.runsLeftToday -= 1
    const id = `mock-${Math.random().toString(36).slice(2, 10)}`
    state.runs[id] = { id, start: Date.now() + 300, followups: [] }
    save()
    return { run_id: id }
  },
  async run(id) {
    await wait(120)
    requireAuth()
    return buildResult(getRun(id))
  },
  async followup(id, question) {
    await wait(300)
    requireAuth()
    const run = getRun(id)
    const r = buildResult(run)
    if (r.status !== 'finished') throw new ApiError(409, 'The run is still in progress.')
    run.followups.push({ question, start: Date.now() + 200 })
    save()
    return { run_id: id }
  },
  streamEvents(id: string, after: number, h: StreamHandlers) {
    let last = after
    let stopped = false
    const tick = () => {
      if (stopped) return
      const run = state.runs[id]
      if (!run) return
      for (const ev of visible(run)) {
        if (ev.seq <= last) continue
        last = ev.seq
        h.onEvent(ev)
      }
      if (last >= totalEvents(run)) {
        stopped = true
        clearInterval(timer)
        h.onEnd()
      }
    }
    const timer = setInterval(tick, 90)
    queueMicrotask(() => h.onConnection?.('open'))
    return () => {
      stopped = true
      clearInterval(timer)
    }
  },
}

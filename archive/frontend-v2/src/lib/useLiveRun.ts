import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api'
import type { AnalysisResult, TraceEvent } from '../types'

export type Connection = 'idle' | 'open' | 'retrying' | 'lost'

function mergeEvents(a: TraceEvent[], b: TraceEvent[]): TraceEvent[] {
  if (!b.length) return a
  const bySeq = new Map<number, TraceEvent>()
  for (const e of a) bySeq.set(e.seq, e)
  for (const e of b) bySeq.set(e.seq, e)
  return [...bySeq.values()].sort((x, y) => x.seq - y.seq)
}

const REFRESH_ON = new Set(['node_finished', 'run_finished', 'run_failed'])

/**
 * Live run state: GET the result once, then (while running) subscribe to the SSE stream from the
 * last seq we have. Events append to the trace immediately; whenever a node finishes we re-GET the
 * result so the evidence board fills in section by section. Follow-ups reopen the stream.
 */
export function useLiveRun(id: string) {
  const [result, setResult] = useState<AnalysisResult | null>(null)
  const [events, setEvents] = useState<TraceEvent[]>([])
  const [error, setError] = useState<unknown>(null)
  const [loading, setLoading] = useState(true)
  const [connection, setConnection] = useState<Connection>('idle')
  const [streaming, setStreaming] = useState(false)
  const stopRef = useRef<(() => void) | null>(null)
  const lastSeq = useRef(0)
  const refreshTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const alive = useRef(true)

  const refresh = useCallback(async () => {
    try {
      const r = await api.run(id)
      if (!alive.current) return
      setResult(r)
      setEvents((prev) => mergeEvents(prev, r.trace))
      lastSeq.current = Math.max(lastSeq.current, ...r.trace.map((e) => e.seq), 0)
    } catch (e) {
      if (alive.current) setError((prev: unknown) => prev ?? e)
    }
  }, [id])

  // Throttle, not debounce: a burst of events must not keep postponing the refetch.
  const scheduleRefresh = useCallback(() => {
    if (refreshTimer.current !== undefined) return
    refreshTimer.current = setTimeout(() => {
      refreshTimer.current = undefined
      void refresh()
    }, 120)
  }, [refresh])

  const startStream = useCallback(() => {
    stopRef.current?.()
    setStreaming(true)
    stopRef.current = api.streamEvents(id, lastSeq.current, {
      onEvent: (ev) => {
        lastSeq.current = Math.max(lastSeq.current, ev.seq)
        setEvents((prev) => mergeEvents(prev, [ev]))
        if (REFRESH_ON.has(ev.type)) scheduleRefresh()
      },
      onEnd: () => {
        setStreaming(false)
        setConnection('idle')
        stopRef.current = null
        void refresh()
      },
      onConnection: (s) => setConnection(s),
    })
  }, [id, refresh, scheduleRefresh])

  useEffect(() => {
    alive.current = true
    setLoading(true)
    setError(null)
    setResult(null)
    setEvents([])
    lastSeq.current = 0
    api.run(id).then(
      (r) => {
        if (!alive.current) return
        setResult(r)
        setEvents(r.trace)
        lastSeq.current = Math.max(0, ...r.trace.map((e) => e.seq))
        setLoading(false)
        if (r.status === 'running' || r.status === 'queued') startStream()
      },
      (e) => {
        if (!alive.current) return
        setError(e)
        setLoading(false)
      },
    )
    return () => {
      alive.current = false
      stopRef.current?.()
      stopRef.current = null
      clearTimeout(refreshTimer.current)
      refreshTimer.current = undefined
    }
  }, [id, startStream])

  const followup = useCallback(
    async (question: string) => {
      await api.followup(id, question)
      setResult((r) => (r ? { ...r, status: 'running' } : r))
      startStream()
    },
    [id, startStream],
  )

  const reconnect = useCallback(() => {
    setConnection('idle')
    void refresh().then(startStream)
  }, [refresh, startStream])

  return { result, events, error, loading, connection, streaming, followup, reconnect }
}

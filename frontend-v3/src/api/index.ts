import type { Api, StreamHandlers } from './contract'
import { httpApi } from './http'

export { ApiError } from './client'
export type { AnalyzeInput } from './contract'

/** `VITE_MOCK=1` (default for `npm run dev`) serves src/mock/*.json and simulates SSE. */
export const MOCK = import.meta.env.VITE_MOCK === '1'

// The mock module is only imported in mock mode, so production bundles never contain it.
const impl: Promise<Api> = MOCK ? import('../mock/server').then((m) => m.mockApi) : Promise.resolve(httpApi)

type AsyncKeys = Exclude<keyof Api, 'streamEvents'>

function proxy<K extends AsyncKeys>(key: K): Api[K] {
  return ((...args: unknown[]) => impl.then((a) => (a[key] as (...x: unknown[]) => unknown)(...args))) as Api[K]
}

export const api: Api = {
  me: proxy('me'),
  limits: proxy('limits'),
  login: proxy('login'),
  logout: proxy('logout'),
  showcase: proxy('showcase'),
  showcaseCase: proxy('showcaseCase'),
  samples: proxy('samples'),
  sample: proxy('sample'),
  analyze: proxy('analyze'),
  run: proxy('run'),
  followup: proxy('followup'),
  streamEvents(id: string, after: number, handlers: StreamHandlers) {
    let stop: (() => void) | null = null
    let cancelled = false
    void impl.then((a) => {
      if (!cancelled) stop = a.streamEvents(id, after, handlers)
    })
    return () => {
      cancelled = true
      stop?.()
    }
  },
}

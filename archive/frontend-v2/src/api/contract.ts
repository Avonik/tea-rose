import type {
  AnalysisResult,
  AuthMe,
  Limits,
  RunCreated,
  SampleRef,
  ShowcaseSummary,
  TraceEvent,
} from '../types'

export type AnalyzeInput = { text: string } | { file: File }

export interface StreamHandlers {
  onEvent: (ev: TraceEvent) => void
  /** The stream ended because the run reached a terminal state. */
  onEnd: () => void
  /** Connection dropped; `retrying` is false once we gave up. */
  onConnection?: (state: 'open' | 'retrying' | 'lost') => void
}

/** Everything the UI needs from the backend. Implemented over HTTP and by the mock. */
export interface Api {
  me(): Promise<AuthMe>
  limits(): Promise<Limits>
  login(passcode: string): Promise<void>
  logout(): Promise<void>
  showcase(): Promise<ShowcaseSummary[]>
  showcaseCase(slug: string): Promise<AnalysisResult>
  samples(): Promise<SampleRef[]>
  sample(name: string): Promise<string>
  analyze(input: AnalyzeInput): Promise<RunCreated>
  run(id: string): Promise<AnalysisResult>
  followup(id: string, question: string): Promise<RunCreated>
  /** Subscribe to trace events with seq > after. Returns an unsubscribe function. */
  streamEvents(id: string, after: number, handlers: StreamHandlers): () => void
}

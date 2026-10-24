import type { AnalysisResult, Claim, ProxyResolution, Side, TagOption } from '../types'

/**
 * Round half away from zero at `digits` decimals. `toFixed` alone rounds the binary value, so
 * 0.475 showed as "0.47" while the trace and the memo say 0.48.
 */
export const fixed = (v: number, digits = 2) => {
  const f = 10 ** digits
  const r = Math.round(Math.abs(v) * f + 1e-9) / f
  return (v < 0 && r !== 0 ? -r : r).toFixed(digits)
}

export const pct = (v: number | null | undefined, digits = 0) =>
  v == null || Number.isNaN(v) ? '–' : `${fixed(v * 100, digits)}%`

export const num = (v: number | null | undefined, digits = 2) =>
  v == null || Number.isNaN(v) ? '–' : fixed(v, digits)

export const signed = (v: number | null | undefined, digits = 2) =>
  v == null || Number.isNaN(v) ? '–' : `${v > 0 ? '+' : v < 0 ? '−' : ''}${fixed(Math.abs(v), digits)}`

/**
 * Plain-words reading of a 0–1 percentile inside a peer set. 0.50 is the middle of the pack, which
 * means "no signal either way", not "half overlap". Descriptive bands, never a legal conclusion.
 */
export function readPercentile(p: number | null | undefined): string {
  if (p == null || Number.isNaN(p)) return 'not computable'
  if (p >= 0.9) return 'top tenth of the peer set: an unusually close audience'
  if (p >= 0.65) return 'clearly above the middle of the peer set'
  if (p > 0.35) return 'near the middle of the peer set: no signal either way'
  if (p > 0.1) return 'below the middle of the peer set'
  return 'bottom tenth of the peer set: the audiences barely meet'
}

export const ordinal = (n: number) => `#${n.toLocaleString('en-US')}`

export const CLAIM_LABEL: Record<Claim, string> = {
  likelihood_of_confusion: 'Likelihood of confusion',
  dilution: 'Dilution',
  common_law_priority: 'Common-law priority',
  other: 'Other claim',
}

export const FACTOR_LABEL: Record<string, string> = {
  relatedness_of_goods: 'Relatedness of goods',
  channels_and_purchasers: 'Channels & purchasers',
  bridging_the_gap: 'Bridging the gap',
  fame: 'Fame',
  zone_of_reputation: 'Zone of reputation',
}

export const humanize = (s: string) => {
  const t = s.replace(/[_-]+/g, ' ').trim()
  return t.charAt(0).toUpperCase() + t.slice(1)
}

export const factorLabel = (f: string) => FACTOR_LABEL[f] ?? humanize(f)

export const AGE_LABEL: Record<string, string> = {
  '24_and_younger': '≤24',
  '25_to_29': '25–29',
  '30_to_34': '30–34',
  '35_to_44': '35–44',
  '45_to_54': '45–54',
  '55_and_older': '55+',
}

export function tagOptionId(t: TagOption): string {
  return String(t.id ?? t.tag_id ?? '')
}

/** "urn:tag:category:qloo:pet_supplies" → "Pet supplies" (or the name from a known menu). */
export function tagName(id: string, menus: (ProxyResolution | null | undefined)[] = []): string {
  for (const m of menus) {
    const hit = m?.tag_options.find((t) => tagOptionId(t) === id)
    if (hit?.name) return String(hit.name)
  }
  const last = id.split(':').pop() ?? id
  return humanize(last)
}

/** Display names for both sides, preferring resolved entity names, then marks, then party names. */
export function sideNames(r: AnalysisResult): Record<Side, string> {
  const res = r.resolution
  const ex = r.extraction
  const name = (side: Side) => {
    const rb = res?.[side]
    const proxy = side === 'senior' ? res?.senior_proxy : res?.junior_proxy
    if (rb?.entity_name) return rb.entity_name
    if (rb?.query) return proxy ? rb.query : rb.query
    const p = ex?.[side]
    return p?.marks[0] ? titleCaseMark(p.marks[0]) : p?.name ?? (side === 'senior' ? 'Senior' : 'Junior')
  }
  return { senior: name('senior'), junior: name('junior') }
}

/** Marks are often written in caps in pleadings; show them in title case in prose. */
export function titleCaseMark(m: string) {
  if (m !== m.toUpperCase()) return m
  return m.toLowerCase().replace(/(^|[\s.-])(\p{L})/gu, (_, a: string, b: string) => a + b.toUpperCase())
}

export function formatParams(params: Record<string, unknown>): [string, string][] {
  return Object.entries(params).map(([k, v]) => [k, typeof v === 'string' ? v : JSON.stringify(v)])
}

export function shortId(v: string) {
  return /^[0-9A-F]{8}-[0-9A-F-]{27}$/i.test(v) ? `${v.slice(0, 8)}…` : v
}

export const timeOf = (iso: string) => {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

export const bytes = (n: number) => (n < 1024 ? `${n} B` : n < 1024 * 1024 ? `${(n / 1024).toFixed(0)} KB` : `${(n / 1024 / 1024).toFixed(1)} MB`)

/** "Bad Spaniels" → "Bad Spaniels’", "Jack Daniel’s" stays readable. */
export const possessive = (name: string) => (/s$/i.test(name) ? `${name}’` : `${name}’s`)

import type { ReactNode } from 'react'
import { ApiError } from '../api'
import type { Confidence, FactorLean } from '../types'
import { IconChevron, IconError, IconInfo, IconWarn } from './icons'

export function Spinner({ label }: { label?: string }) {
  return (
    <span role={label ? 'status' : undefined} style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
      <span className="spinner" aria-hidden="true" />
      {label && <span>{label}</span>}
    </span>
  )
}

export function Skeleton({ h = 16, w = '100%', r }: { h?: number | string; w?: number | string; r?: number }) {
  return <div className="skeleton" style={{ height: h, width: w, borderRadius: r }} aria-hidden="true" />
}

export function SkeletonCard({ lines = 3 }: { lines?: number }) {
  return (
    <div className="card" aria-hidden="true">
      <Skeleton h={14} w="30%" />
      <div style={{ height: 14 }} />
      {Array.from({ length: lines }, (_, i) => (
        <div key={i} style={{ marginTop: 10 }}>
          <Skeleton h={12} w={`${90 - i * 14}%`} />
        </div>
      ))}
    </div>
  )
}

export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) return err.detail || err.message
  if (err instanceof Error) return err.message
  return 'Something went wrong.'
}

export function StateView({
  kind,
  title,
  body,
  action,
}: {
  kind: 'loading' | 'empty' | 'error'
  title: string
  body?: ReactNode
  action?: ReactNode
}) {
  return (
    <div className={`state state--${kind}`} role={kind === 'error' ? 'alert' : 'status'}>
      <div className="state__icon">
        {kind === 'loading' ? <span className="spinner" aria-hidden="true" /> : kind === 'error' ? <IconError size={20} /> : <IconInfo size={20} />}
      </div>
      <div className="state__title">{title}</div>
      {body && <div className="state__body">{body}</div>}
      {action}
    </div>
  )
}

export function ErrorState({ error, onRetry, title = 'Could not load this' }: { error: unknown; onRetry?: () => void; title?: string }) {
  return (
    <StateView
      kind="error"
      title={title}
      body={errorMessage(error)}
      action={
        onRetry && (
          <button className="btn btn--sm" onClick={onRetry}>
            Try again
          </button>
        )
      }
    />
  )
}

export function Notice({ kind, children }: { kind: 'warn' | 'error' | 'info'; children: ReactNode }) {
  const Icon = kind === 'warn' ? IconWarn : kind === 'error' ? IconError : IconInfo
  return (
    <div className={`notice notice--${kind}`} role={kind === 'error' ? 'alert' : undefined}>
      <Icon size={16} />
      <div>{children}</div>
    </div>
  )
}

export const LEAN_LABEL: Record<FactorLean, string> = {
  favors_senior: 'Favors senior',
  neutral: 'Neutral',
  favors_junior: 'Favors junior',
  insufficient_data: 'Insufficient data',
}

const LEAN_CLASS: Record<FactorLean, string> = {
  favors_senior: 'chip--senior',
  neutral: 'chip--neutral',
  favors_junior: 'chip--junior',
  insufficient_data: 'chip--insufficient',
}

export function LeanChip({ lean }: { lean: FactorLean }) {
  return (
    <span className={`chip ${LEAN_CLASS[lean] ?? 'chip--neutral'}`}>
      {lean !== 'insufficient_data' && <span className="chip__dot" aria-hidden="true" />}
      {LEAN_LABEL[lean] ?? lean}
    </span>
  )
}

export function ConfidenceMeter({ level }: { level: Confidence }) {
  const n = level === 'high' ? 3 : level === 'medium' ? 2 : 1
  return (
    <span className="confidence" title={`${level} confidence`}>
      <span className="confidence__bars" aria-hidden="true">
        {[1, 2, 3].map((i) => (
          <span key={i} data-on={i <= n} />
        ))}
      </span>
      <span className="confidence__label">{level}</span>
    </span>
  )
}

export function Disclosure({
  summary,
  children,
  className = '',
  defaultOpen,
  printOpen = true,
}: {
  summary: ReactNode
  children: ReactNode
  className?: string
  defaultOpen?: boolean
  printOpen?: boolean
}) {
  return (
    <details className={`disclosure ${className}`} open={defaultOpen} data-print-open={printOpen || undefined}>
      <summary>
        <IconChevron className="disclosure__chev" size={14} />
        {summary}
      </summary>
      {children}
    </details>
  )
}

export function Meter({ value, color, label }: { value: number; color?: string; label?: string }) {
  const pct = Math.max(0, Math.min(1, value)) * 100
  return (
    <div className="meter" role="img" aria-label={label ?? `${Math.round(pct)}%`}>
      <div className="meter__fill" style={{ width: `${pct}%`, background: color }} />
    </div>
  )
}

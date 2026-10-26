import { AnimatePresence, LayoutGroup, motion, useReducedMotion } from 'motion/react'
import { useId, useState, type ReactNode } from 'react'
import { ApiError } from '../api'
import { fade, springQuick } from '../motion/springs'
import type { Confidence, FactorLean } from '../types'
import { IconChevron, IconError, IconInfo, IconWarn, IconCheckCircle } from './icons'

// ------------------------------------------------------------------ status & feedback

export function Spinner({ label, size }: { label?: string; size?: 'sm' }) {
  return (
    <span role={label ? 'status' : undefined} className="spinner-wrap">
      <span className={`spinner ${size === 'sm' ? 'spinner--sm' : ''}`} aria-hidden="true" />
      {label && <span>{label}</span>}
    </span>
  )
}

export function Skeleton({ h = 14, w = '100%', r }: { h?: number | string; w?: number | string; r?: number }) {
  return <span className="skeleton" style={{ height: h, width: w, borderRadius: r }} aria-hidden="true" />
}

/** A labelled placeholder that holds a block's place while a run streams. */
export function SkeletonCard({ lines = 3, label, tall }: { lines?: number; label?: string; tall?: boolean }) {
  return (
    <div className="skeleton-block" aria-busy="true" aria-label={label} style={tall ? { minHeight: '18rem' } : undefined}>
      {label && (
        <p className="caption pending-label">
          <span className="spinner spinner--sm" aria-hidden="true" /> {label}
        </p>
      )}
      <Skeleton h={22} w="38%" />
      {Array.from({ length: lines }, (_, i) => (
        <Skeleton key={i} h={12} w={`${92 - i * 14}%`} />
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
      <div className="state__icon" aria-hidden="true">
        {kind === 'loading' ? <span className="spinner" /> : kind === 'error' ? <IconError size={22} /> : <IconInfo size={22} />}
      </div>
      <h1 className="state__title">{title}</h1>
      {body && <div className="state__body">{body}</div>}
      {action && <div className="state__action">{action}</div>}
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
          <button type="button" className="btn btn--primary" onClick={onRetry}>
            Try again
          </button>
        )
      }
    />
  )
}

/** Status in four kinds: warning, error, info, success. Always icon + label. */
export function Notice({ kind, children, title }: { kind: 'warn' | 'error' | 'info' | 'ok'; children: ReactNode; title?: string }) {
  const Icon = kind === 'warn' ? IconWarn : kind === 'error' ? IconError : kind === 'ok' ? IconCheckCircle : IconInfo
  return (
    <div className={`notice notice--${kind}`} role={kind === 'error' ? 'alert' : kind === 'warn' ? 'status' : undefined}>
      <Icon size={17} />
      <div>
        {title && <strong className="notice__title">{title} </strong>}
        {children}
      </div>
    </div>
  )
}

// ------------------------------------------------------------------ chips

export const LEAN_LABEL: Record<FactorLean, string> = {
  favors_senior: 'Favors senior',
  neutral: 'Neutral',
  favors_junior: 'Favors junior',
  insufficient_data: 'Insufficient data',
}

/** A lean is data: the dot carries the party colour (gray for neutral, hollow for no data); the label stays ink. */
export function LeanChip({ lean, size, names }: { lean: FactorLean; size?: 'sm'; names?: { senior: string; junior: string } }) {
  const label = names && lean === 'favors_senior' ? `Favors ${names.senior}` : names && lean === 'favors_junior' ? `Favors ${names.junior}` : LEAN_LABEL[lean] ?? lean
  return (
    <span className={`chip lean--${lean} ${size === 'sm' ? 'chip--sm' : ''}`}>
      <span className={`dot ${lean === 'insufficient_data' ? 'dot--hollow' : ''}`} aria-hidden="true" />
      {label}
    </span>
  )
}

export function ConfidenceMeter({ level }: { level: Confidence }) {
  const n = level === 'high' ? 3 : level === 'medium' ? 2 : 1
  return (
    <span className="confidence" aria-label={`${level} confidence`}>
      <span className="confidence__bars" aria-hidden="true">
        {[1, 2, 3].map((i) => (
          <span key={i} data-on={i <= n || undefined} />
        ))}
      </span>
      <span aria-hidden="true">{level.charAt(0).toUpperCase() + level.slice(1)} confidence</span>
    </span>
  )
}

// ------------------------------------------------------------------ disclosure (interruptible height spring)

export function Disclosure({
  summary,
  children,
  className = '',
  defaultOpen = false,
  printOpen = true,
  id,
  open: openProp,
  onOpenChange,
}: {
  summary: ReactNode
  children: ReactNode
  className?: string
  defaultOpen?: boolean
  printOpen?: boolean
  id?: string
  /** Controlled mode (optional): the parent owns the open state. */
  open?: boolean
  onOpenChange?: (open: boolean) => void
}) {
  const [openState, setOpenState] = useState(defaultOpen)
  const open = openProp ?? openState
  const setOpen = (fn: (o: boolean) => boolean) => {
    const next = fn(open)
    if (openProp === undefined) setOpenState(next)
    onOpenChange?.(next)
  }
  const reduce = useReducedMotion()
  const autoId = useId()
  const bodyId = id ?? autoId
  return (
    <div className={`disclosure ${className}`} data-open={open || undefined} data-print-open={printOpen || undefined}>
      <button type="button" className="disclosure__summary pressable" aria-expanded={open} aria-controls={bodyId} onClick={() => setOpen((o) => !o)}>
        <motion.span className="disclosure__chev" animate={{ rotate: open ? 90 : 0 }} transition={reduce ? fade : springQuick} aria-hidden="true">
          <IconChevron size={14} />
        </motion.span>
        <span className="disclosure__label">{summary}</span>
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            id={bodyId}
            className="disclosure__body"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={reduce ? fade : springQuick}
            style={{ overflow: 'hidden' }}
          >
            <div className="disclosure__inner">{children}</div>
          </motion.div>
        )}
      </AnimatePresence>
      {!open && printOpen && <div className="disclosure__print-only">{children}</div>}
    </div>
  )
}

// ------------------------------------------------------------------ meter & segmented control

export function Meter({ value, color, label, height = 6 }: { value: number; color?: string; label?: string; height?: number }) {
  const reduce = useReducedMotion()
  const p = Math.max(0, Math.min(1, value))
  return (
    <div className="meter" role="img" aria-label={label ?? `${Math.round(p * 100)}%`} style={{ height }}>
      <motion.div
        className="meter__fill"
        style={{ background: color }}
        initial={{ scaleX: 0 }}
        animate={{ scaleX: p }}
        transition={reduce ? fade : { type: 'spring', bounce: 0, duration: 0.6 }}
      />
    </div>
  )
}

export interface SegmentOption<T extends string> {
  value: T
  label: ReactNode
  icon?: ReactNode
  disabled?: boolean
  title?: string
}

/** A segmented control whose selection indicator slides between segments (shared layout spring). */
export function Segmented<T extends string>({
  value,
  onChange,
  options,
  label,
  size,
  className = '',
}: {
  value: T
  onChange: (v: T) => void
  options: SegmentOption<T>[]
  label: string
  size?: 'sm'
  className?: string
}) {
  const reduce = useReducedMotion()
  const group = useId()
  return (
    <LayoutGroup id={group}>
      <div className={`segmented ${size === 'sm' ? 'segmented--sm' : ''} ${className}`} role="radiogroup" aria-label={label}>
        {options.map((o) => {
          const on = o.value === value
          return (
            <button
              key={o.value}
              type="button"
              role="radio"
              aria-checked={on}
              className="segmented__item pressable"
              disabled={o.disabled}
              title={o.title}
              onClick={() => onChange(o.value)}
            >
              {on && <motion.span layoutId="seg-indicator" className="segmented__indicator" transition={reduce ? fade : springQuick} aria-hidden="true" />}
              <span className="segmented__content">
                {o.icon}
                {o.label}
              </span>
            </button>
          )
        })}
      </div>
    </LayoutGroup>
  )
}

// ------------------------------------------------------------------ verdict chips

type VerdictChip = { label: string; side: 'senior' | 'junior' | null }

/**
 * Two one-word verdicts before the sentences: "Court: Vans" and "Tea Rose: Too close". The dot carries the
 * brand's party colour where a brand is named; Mixed, Settled and Too close keep the neutral grey dot.
 */
export function VerdictChips({ court, read }: { court: VerdictChip; read?: VerdictChip | null }) {
  const one = (k: string, c: VerdictChip) => (
    <span className="chip chip--sm verdict-chip">
      <span className="verdict-chip__k">{k}:</span>
      <span className={`dot ${c.side ? `dot--${c.side}` : ''}`} aria-hidden="true" />
      {c.label}
    </span>
  )
  return (
    <span className="chips verdict-chips">
      {one('Court', court)}
      {read && one('Tea Rose', read)}
    </span>
  )
}

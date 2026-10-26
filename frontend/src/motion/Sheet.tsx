import { animate, motion, useMotionValue, useReducedMotion, useTransform } from 'motion/react'
import { useCallback, useEffect, useLayoutEffect, useRef, useState, type PointerEvent as RPointerEvent, type ReactNode } from 'react'
import { nearest, project, rubberband, springSheet, VelocityTracker } from './springs'
import './sheet.css'

export type Snap = 'peek' | 'half' | 'full'
const ORDER: Snap[] = ['peek', 'half', 'full']

/**
 * A bottom sheet that behaves like a physical object: it tracks the finger 1:1 from where it was
 * grabbed, rubber-bands past its limits, projects a flick to where it would come to rest, snaps to
 * the nearest detent and hands the release velocity to the spring. Any motion can be grabbed and
 * reversed mid-flight because the spring starts from the current on-screen position.
 */
export function Sheet({
  snap,
  onSnap,
  header,
  children,
  peekHeight = 76,
  halfRatio = 0.5,
  fullRatio = 0.92,
  label,
}: {
  snap: Snap
  onSnap: (s: Snap) => void
  header: ReactNode
  children: ReactNode
  peekHeight?: number
  halfRatio?: number
  fullRatio?: number
  label: string
}) {
  const reduce = useReducedMotion()
  const [vh, setVh] = useState(() => (typeof window === 'undefined' ? 800 : window.innerHeight))
  useEffect(() => {
    const on = () => setVh(window.innerHeight)
    window.addEventListener('resize', on)
    return () => window.removeEventListener('resize', on)
  }, [])

  const fullH = Math.round(vh * fullRatio)
  // y is the sheet's translateY in px. 0 = fully open; larger = lower.
  const snapY: Record<Snap, number> = {
    full: 0,
    half: Math.round(fullH - vh * halfRatio),
    peek: fullH - peekHeight,
  }
  const minY = snapY.full
  const maxY = snapY.peek

  const y = useMotionValue(snapY[snap])
  const scrim = useTransform(y, [snapY.half, snapY.peek], [0.55, 0])
  const scrimEvents = useTransform(y, (v) => (v < snapY.peek - 4 ? 'auto' : 'none'))
  const ref = useRef<HTMLDivElement>(null)
  const bodyRef = useRef<HTMLDivElement>(null)
  const tracker = useRef(new VelocityTracker())
  const drag = useRef<{ startY: number; startVal: number; pointerId: number; fromBody: boolean } | null>(null)
  const [dragging, setDragging] = useState(false)
  const [current, setCurrent] = useState<Snap>(snap)

  const settle = useCallback(
    (target: Snap, velocity = 0) => {
      setCurrent(target)
      onSnap(target)
      if (reduce) return animate(y, snapY[target], { type: 'tween', duration: 0.2, ease: 'easeOut' })
      return animate(y, snapY[target], { ...springSheet, velocity })
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [onSnap, reduce, snapY.full, snapY.half, snapY.peek],
  )

  // Follow external snap changes (e.g. a button that opens the sheet) and viewport changes.
  useLayoutEffect(() => {
    if (drag.current) return
    if (snap !== current) {
      settle(snap)
      return
    }
    // Keep the detent on resize without animating.
    y.set(snapY[current])
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [snap, vh])

  function onPointerDown(e: RPointerEvent<HTMLDivElement>, fromBody: boolean) {
    if (e.button !== 0 && e.pointerType === 'mouse') return
    // When fully open, the body scrolls; only a drag that starts at the top edge grabs the sheet.
    if (fromBody && current === 'full' && (bodyRef.current?.scrollTop ?? 0) > 0) return
    y.stop() // grab mid-flight
    drag.current = { startY: e.clientY, startVal: y.get(), pointerId: e.pointerId, fromBody }
    tracker.current.reset()
    tracker.current.push(y.get())
    ;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
    setDragging(true)
  }

  function onPointerMove(e: RPointerEvent<HTMLDivElement>) {
    const d = drag.current
    if (!d || e.pointerId !== d.pointerId) return
    const dy = e.clientY - d.startY
    if (d.fromBody && current === 'full' && dy < 0) return // scrolling up inside the body, not a drag
    let next = d.startVal + dy
    if (next < minY) next = minY + rubberband(next - minY, fullH)
    if (next > maxY) next = maxY + rubberband(next - maxY, fullH)
    y.set(next)
    tracker.current.push(next)
  }

  function onPointerUp(e: RPointerEvent<HTMLDivElement>) {
    const d = drag.current
    if (!d || e.pointerId !== d.pointerId) return
    drag.current = null
    setDragging(false)
    const v = tracker.current.velocity()
    const projected = y.get() + project(v, 0.995)
    const targetY = nearest(projected, [snapY.full, snapY.half, snapY.peek])
    const target = (Object.keys(snapY) as Snap[]).find((k) => snapY[k] === targetY) ?? 'peek'
    // A flick with real momentum decides by direction even if the projection falls short.
    let chosen = target
    if (Math.abs(v) > 900) {
      const i = ORDER.indexOf(current)
      chosen = v < 0 ? ORDER[Math.min(2, i + 1)] : ORDER[Math.max(0, i - 1)]
    }
    settle(chosen, v)
  }

  const bodyScrolls = current === 'full' && !dragging

  return (
    <>
      <motion.div
        className="sheet-scrim"
        style={{ opacity: scrim, pointerEvents: scrimEvents }}
        onClick={() => settle('peek')}
        aria-hidden="true"
      />
      <motion.section
        ref={ref}
        className="sheet"
        style={{ y, height: fullH }}
        data-snap={current}
        data-dragging={dragging || undefined}
        aria-label={label}
      >
        <div
          className="sheet__grab"
          onPointerDown={(e) => onPointerDown(e, false)}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerCancel={onPointerUp}
        >
          <button
            type="button"
            className="sheet__handle"
            aria-label={current === 'peek' ? 'Expand panel' : 'Collapse panel'}
            onClick={() => settle(current === 'peek' ? 'half' : 'peek')}
          >
            <span />
          </button>
          <div className="sheet__header">{header}</div>
        </div>
        <div
          ref={bodyRef}
          className="sheet__body"
          style={{ overflowY: bodyScrolls ? 'auto' : 'hidden', touchAction: bodyScrolls ? 'pan-y' : 'none' }}
          onPointerDown={(e) => onPointerDown(e, true)}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerCancel={onPointerUp}
        >
          {children}
        </div>
      </motion.section>
    </>
  )
}

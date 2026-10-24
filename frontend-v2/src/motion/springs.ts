/**
 * Motion vocabulary, in Apple's two parameters (damping ratio, response) mapped onto Motion's
 * `bounce` + `duration` spring API. bounce ≈ 1 − damping; duration ≈ response.
 *
 * - Default UI: critically damped (no overshoot). Calm, never distracting.
 * - Gesture: a little bounce, only because the user's own momentum preceded it.
 *
 * Every spring here animates from the current presentation value, so an interrupted motion
 * continues from where it is instead of jumping to its logical start.
 */
import type { Transition } from 'motion/react'

/** damping 1.0, response 0.4: moving and repositioning (Apple's PiP values) */
export const spring: Transition = { type: 'spring', bounce: 0, duration: 0.4 }

/** damping 1.0, response 0.3: small UI (chips, disclosures, menus) */
export const springQuick: Transition = { type: 'spring', bounce: 0, duration: 0.3 }

/** damping 1.0, response 0.55: large surfaces and number count-ups */
export const springSlow: Transition = { type: 'spring', bounce: 0, duration: 0.55 }

/** damping ~0.8, response 0.3: drawers and sheets after a flick (Apple's sheet values) */
export const springSheet: Transition = { type: 'spring', bounce: 0.18, duration: 0.34 }

/** Reduced motion: a short cross-fade, no travel */
export const fade: Transition = { type: 'tween', duration: 0.18, ease: 'easeOut' }

/**
 * Where a flick would come to rest under scroll-style deceleration. Apple's exact projection from
 * the Designing Fluid Interfaces sample code (exponential decay, not v²/2a).
 * @param velocity px/s
 * @param decelerationRate 0.998 normal scroll feel, 0.99 snappier
 */
export function project(velocity: number, decelerationRate = 0.998): number {
  return ((velocity / 1000) * decelerationRate) / (1 - decelerationRate)
}

/**
 * Progressive resistance past a boundary: the further past it, the less the element follows.
 * @param overshoot distance past the bound (same sign as the drag)
 * @param dimension the size of the surface being dragged
 */
export function rubberband(overshoot: number, dimension: number, constant = 0.55): number {
  return (overshoot * dimension * constant) / (dimension + constant * Math.abs(overshoot))
}

/** The snap point whose value is nearest to `x`. */
export function nearest(x: number, snaps: number[]): number {
  let best = snaps[0]
  for (const s of snaps) if (Math.abs(s - x) < Math.abs(best - x)) best = s
  return best
}

/**
 * Velocity from a short history of (time, value) samples: only the last ~100 ms count, so a pause
 * before release reads as zero velocity, the way a finger that stops feels.
 */
export class VelocityTracker {
  private samples: { t: number; v: number }[] = []

  reset() {
    this.samples = []
  }

  push(value: number, time = performance.now()) {
    this.samples.push({ t: time, v: value })
    const cutoff = time - 120
    while (this.samples.length > 2 && this.samples[0].t < cutoff) this.samples.shift()
  }

  /** px/s; 0 if there is not enough recent movement */
  velocity(now = performance.now()): number {
    const s = this.samples
    if (s.length < 2) return 0
    const last = s[s.length - 1]
    if (now - last.t > 80) return 0
    const first = s[0]
    const dt = last.t - first.t
    if (dt <= 0) return 0
    return ((last.v - first.v) / dt) * 1000
  }
}

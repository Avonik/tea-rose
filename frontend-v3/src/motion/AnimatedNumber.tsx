import { animate, useMotionValue, useReducedMotion } from 'motion/react'
import { useEffect, useState } from 'react'
import { fixed } from '../lib/format'
import { springSlow } from './springs'

/**
 * A number that settles onto its value with a spring, starting from whatever it currently shows.
 * Re-targeting mid-flight carries the current value forward, so a run whose score updates twice
 * never jumps. Reduced motion: the value appears at once.
 */
export function AnimatedNumber({
  value,
  digits = 2,
  format,
  className,
}: {
  value: number | null | undefined
  digits?: number
  format?: (v: number) => string
  className?: string
}) {
  const reduce = useReducedMotion()
  const mv = useMotionValue(0)
  const [shown, setShown] = useState<string>(value == null ? '–' : fmt(value))
  function fmt(v: number) {
    return format ? format(v) : fixed(v, digits)
  }

  useEffect(() => {
    if (value == null || Number.isNaN(value)) {
      setShown('–')
      return
    }
    if (reduce) {
      mv.set(value)
      setShown(fmt(value))
      return
    }
    const controls = animate(mv, value, { ...springSlow, onUpdate: (v) => setShown(fmt(v)) })
    return () => controls.stop()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value, reduce, digits])

  return (
    <span className={`num ${className ?? ''}`} aria-label={value == null ? undefined : fmt(value)}>
      {shown}
    </span>
  )
}

import { motion, useReducedMotion, type HTMLMotionProps } from 'motion/react'
import type { ReactNode } from 'react'
import { fade, spring, springQuick } from './springs'

type Props = HTMLMotionProps<'div'> & {
  children: ReactNode
  /** Direction things arrive from. Lists grow downward, so new rows come from below. */
  from?: 'below' | 'above' | 'none'
  /** Stagger index for lists; 40 ms per step, capped. */
  index?: number
  distance?: number
  quick?: boolean
}

/**
 * Enter/exit with a critically damped rise. Under reduced motion it is a plain cross-fade.
 * Exits go back the way they came (spatial consistency).
 */
export function Reveal({ children, from = 'below', index = 0, distance = 10, quick = false, ...rest }: Props) {
  const reduce = useReducedMotion()
  const y = from === 'none' || reduce ? 0 : from === 'below' ? distance : -distance
  const delay = Math.min(index, 8) * 0.04
  return (
    <motion.div
      initial={{ opacity: 0, y }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y }}
      transition={reduce ? { ...fade, delay } : { ...(quick ? springQuick : spring), delay }}
      {...rest}
    >
      {children}
    </motion.div>
  )
}

/** Page root: a short rise on mount only (navigations are not sheets; no exit travel). */
export function Page({ children, className }: { children: ReactNode; className?: string }) {
  const reduce = useReducedMotion()
  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, y: reduce ? 0 : 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={reduce ? fade : spring}
    >
      {children}
    </motion.div>
  )
}

import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { IconChevron } from '../components/icons'
import { LeanChip, SkeletonCard } from '../components/ui'
import { factorLabel } from '../lib/format'
import { fade, spring } from '../motion/springs'
import type { Memo } from '../types'

/**
 * The memo's answer at the top of the page, so the verdict is legible before the evidence. The slot
 * is reserved as soon as a memo is expected, so nothing above the reader shifts when it lands.
 */
export default function BottomLine({ memo, expected, names }: { memo: Memo | null; expected: boolean; names?: { senior: string; junior: string } }) {
  const reduce = useReducedMotion()
  if (!memo && !expected) return null
  const n = memo?.appendix_queries.length ?? 0
  return (
    <div className="slot bottom-line-slot" id="bottom-line">
      <AnimatePresence initial={false} mode="popLayout">
        {memo ? (
          <motion.section
            key="memo"
            className="bottom-line"
            aria-labelledby="bottom-line-title"
            initial={{ opacity: 0, y: reduce ? 0 : 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={reduce ? fade : spring}
          >
            <p className="eyebrow" id="bottom-line-title">
              Bottom line
            </p>
            <p className="bottom-line__headline serif">{memo.headline}</p>
            {memo.bottom_line && <p className="bottom-line__summary">{memo.bottom_line}</p>}
            {memo.findings.length > 0 && (
              <ul className="bottom-line__leans" aria-label="Factor findings">
                {memo.findings.map((f) => (
                  <li key={f.factor}>
                    <span className="bottom-line__factor">{factorLabel(f.factor)}</span>
                    <span className="bottom-line__arrow" aria-hidden="true">
                      →
                    </span>
                    <LeanChip lean={f.lean} size="sm" names={names} />
                  </li>
                ))}
              </ul>
            )}
            <p className="bottom-line__foot footnote secondary">
              <span>
                Every score below traces to one of <span className="num">{n}</span> logged Qloo {n === 1 ? 'query' : 'queries'}.
              </span>
              <a href="#meaning" className="bottom-line__read">
                What this means <IconChevron size={12} />
              </a>
            </p>
          </motion.section>
        ) : (
          <motion.div key="skeleton" initial={false} exit={{ opacity: 0 }} transition={fade}>
            <SkeletonCard lines={2} label="Bottom line: waiting for the memo" />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

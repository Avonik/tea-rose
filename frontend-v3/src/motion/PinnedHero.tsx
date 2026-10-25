import { motion, useMotionValueEvent, useReducedMotion, useScroll, useTransform } from 'motion/react'
import { useRef, useState, type FocusEvent } from 'react'
import { Link } from 'react-router-dom'
import { COUNTDOWN, HERO, tickUnit, type Tick } from '../content/home'

/**
 * The home hero, pinned to scroll (docs/SITE_STORY.md §1). One progress value, read straight from
 * the scroll position of a ~320vh track, drives one idea per beat:
 *
 *   0.00–0.08  hold     "6 weeks" over "$15,000 to $100,000. Six to eight weeks."
 *   0.08–0.58  clock    the numeral counts down like a clock: weeks, days, hours, minutes, to "1 minute"
 *   0.555–0.65 answer   the stake line fades out, then the Tea Rose line fades in (never both at once)
 *   0.72–0.84  promise  the clock recedes, the headline and the two pills settle
 *   0.84–1.00  hold, then the sticky stage scrolls away with the page
 *
 * Nothing autoplays and nothing captures the wheel: every frame is a pure function of where the
 * reader is, so scrolling back runs the clock forward again. Under prefers-reduced-motion the beats
 * render stacked in normal flow, with no pinning.
 *
 * The ticking numeral is visual only (aria-hidden); assistive tech reads HERO.sr once.
 */
export function PinnedHero({ caseHref }: { caseHref: string }) {
  const reduce = useReducedMotion()
  return reduce ? <StaticHero caseHref={caseHref} /> : <ScrollHero caseHref={caseHref} />
}

const CLOCK_START = 0.08
const CLOCK_END = 0.58

/** The numeral and its unit in two fixed-width boxes, so a changing tick never moves anything. */
function Clock({ tick }: { tick: Tick }) {
  return (
    <p className="hero-clock" aria-hidden="true">
      <span className="hero-clock__n num">{tick.n}</span>
      <span className="hero-clock__unit">{tickUnit(tick)}</span>
    </p>
  )
}

function Stake() {
  return (
    <>
      <strong className="hero-pin__money num">{HERO.money}</strong> <span className="hero-pin__weeks">{HERO.weeks}</span>
    </>
  )
}

function HeroPromise({ caseHref }: { caseHref: string }) {
  return (
    <>
      <h1 id="hero-title" className="t-display hero-pin__title">
        {HERO.title}
      </h1>
      <p className="t-subtitle hero-pin__promise">{HERO.promise}</p>
      <div className="hero-pin__actions">
        <Link to={caseHref} className="btn btn--primary btn--lg">
          {HERO.openCase}
        </Link>
        <Link to="/analyze" className="btn btn--lg">
          {HERO.analyze}
        </Link>
      </div>
    </>
  )
}

function ScrollHero({ caseHref }: { caseHref: string }) {
  const track = useRef<HTMLDivElement>(null)
  const { scrollYProgress: p } = useScroll({ target: track, offset: ['start start', 'end end'] })

  // The clock: progress maps linearly onto the tick list; floor keeps each tick for an equal stretch.
  const tickAt = (v: number) => {
    const t = (v - CLOCK_START) / (CLOCK_END - CLOCK_START)
    return Math.max(0, Math.min(COUNTDOWN.length - 1, Math.floor(t * COUNTDOWN.length)))
  }
  const [tick, setTick] = useState(() => tickAt(p.get()))

  // The answer: eyebrow and subline swap once the clock has reached a minute.
  const stakeOpacity = useTransform(p, [0.555, 0.59], [1, 0])
  const answerOpacity = useTransform(p, [0.6, 0.65], [0, 1])
  const answerY = useTransform(p, [0.6, 0.65], [10, 0])

  // The promise: the clock recedes, the headline settles.
  const figOpacity = useTransform(p, [0.72, 0.8], [1, 0])
  const figScale = useTransform(p, [0.72, 0.8], [1, 0.96])
  const figY = useTransform(p, [0.72, 0.8], [0, -24])
  const promiseOpacity = useTransform(p, [0.76, 0.86], [0, 1])
  const promiseY = useTransform(p, [0.76, 0.86], [28, 0])
  // Function form on purpose: a range that starts at 0 is hardware-accelerated onto a ScrollTimeline,
  // which reads as 0 (hidden) at the very top of the page.
  const hintOpacity = useTransform(p, (v) => 1 - Math.min(1, Math.max(0, v / 0.04)))

  // Invisible layers must not catch clicks; pills become live once the promise is mostly in.
  const [promiseLive, setPromiseLive] = useState(false)
  useMotionValueEvent(p, 'change', (v) => {
    setTick(tickAt(v))
    setPromiseLive(v >= 0.8)
  })

  // Keyboard: tabbing into the pills while the promise is still hidden scrolls to the last beat.
  function onPromiseFocus(e: FocusEvent<HTMLDivElement>) {
    const el = track.current
    if (!el || p.get() >= 0.86 || !e.currentTarget.contains(e.target)) return
    const top = el.getBoundingClientRect().top + window.scrollY
    const travel = el.offsetHeight - window.innerHeight
    window.scrollTo({ top: top + travel * 0.9, behavior: 'auto' })
  }

  return (
    <section className="band band--alt hero-pin" aria-labelledby="hero-title">
      <p className="sr-only">
        {HERO.sr} {HERO.source}
      </p>
      <div ref={track} className="hero-pin__track">
        <div className="hero-pin__stage">
          <motion.div className="hero-pin__layer hero-pin__figure" style={{ opacity: figOpacity, scale: figScale, y: figY }} aria-hidden="true">
            <div className="hero-pin__swap hero-pin__eyebrows">
              <motion.p className="eyebrow" style={{ opacity: stakeOpacity }}>
                {HERO.eyebrow}
              </motion.p>
              <motion.p className="eyebrow" style={{ opacity: answerOpacity }}>
                {HERO.endEyebrow}
              </motion.p>
            </div>
            <Clock tick={COUNTDOWN[tick]} />
            <div className="hero-pin__swap hero-pin__lines">
              <motion.div className="hero-pin__line" style={{ opacity: stakeOpacity }}>
                <p className="t-subtitle">
                  <Stake />
                </p>
                <p className="caption tertiary hero-pin__source">{HERO.source}</p>
              </motion.div>
              <motion.div className="hero-pin__line" style={{ opacity: answerOpacity, y: answerY }}>
                <p className="t-subtitle hero-pin__answer">{HERO.end}</p>
              </motion.div>
            </div>
          </motion.div>

          <motion.div
            className="hero-pin__layer hero-pin__finale"
            style={{ opacity: promiseOpacity, y: promiseY, pointerEvents: promiseLive ? 'auto' : 'none' }}
            onFocus={onPromiseFocus}
          >
            <HeroPromise caseHref={caseHref} />
          </motion.div>

          <motion.p className="caption tertiary hero-pin__hint" style={{ opacity: hintOpacity }} aria-hidden="true">
            {HERO.hint}
            <span className="hero-pin__hint-line" />
          </motion.p>
        </div>
      </div>
    </section>
  )
}

function StaticHero({ caseHref }: { caseHref: string }) {
  return (
    <section className="band band--alt hero-static" aria-labelledby="hero-title">
      <p className="sr-only">
        {HERO.sr} {HERO.source}
      </p>
      <div className="wrap hero-static__beats">
        <div className="hero-static__beat" aria-hidden="true">
          <p className="eyebrow">{HERO.eyebrow}</p>
          <Clock tick={COUNTDOWN[0]} />
          <p className="t-subtitle">
            <Stake />
          </p>
          <p className="caption tertiary hero-pin__source">{HERO.source}</p>
        </div>
        <div className="hero-static__beat" aria-hidden="true">
          <p className="eyebrow">{HERO.endEyebrow}</p>
          <Clock tick={COUNTDOWN[COUNTDOWN.length - 1]} />
          <p className="t-subtitle hero-pin__answer">{HERO.end}</p>
        </div>
        <div className="hero-static__beat">
          <HeroPromise caseHref={caseHref} />
        </div>
      </div>
    </section>
  )
}

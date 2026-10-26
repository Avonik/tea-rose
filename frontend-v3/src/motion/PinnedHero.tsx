import { motion, useMotionValueEvent, useReducedMotion, useScroll, useTransform } from 'motion/react'
import { useEffect, useRef, useState, type FocusEvent } from 'react'
import { Link } from 'react-router-dom'
import { IconRose } from '../components/icons'
import { COUNTDOWN, HERO, tickUnit, type Tick } from '../content/home'

/**
 * The home hero, pinned to scroll (docs/SITE_STORY.md §1), on a black stage in both colour schemes.
 * One progress value, read straight from the scroll position of a ~320svh track, drives three beats:
 *
 *   0.00–0.08  beat 1   "6 weeks" over "A consumer survey. $15,000 to $100,000." and its source
 *   0.08–0.58  beat 2   the numeral counts down like a clock to "1 minute"; early on, the survey line
 *                       fades out and the Tea Rose line fades in (never both at once)
 *   0.72–0.84  beat 3   the clock recedes, the headline and the two pills settle
 *   0.84–1.00  hold, then the sticky stage scrolls away with the page
 *
 * The brand mark stays put through every beat; only what is below it changes. Nothing autoplays
 * and nothing captures the wheel: every frame is a pure function of where the reader is, so
 * scrolling back runs the clock forward again. Under prefers-reduced-motion the beats render
 * stacked in normal flow, with no pinning.
 *
 * The ticking numeral is visual only (aria-hidden); assistive tech reads HERO.sr once.
 */
export function PinnedHero({ caseHref }: { caseHref: string }) {
  const reduce = useReducedMotion()
  return reduce ? <StaticHero caseHref={caseHref} /> : <ScrollHero caseHref={caseHref} />
}

const CLOCK_START = 0.08
const CLOCK_END = 0.58

/** The rose glyph and the word, one unit. */
function Mark() {
  return (
    <p className="hero-mark">
      <IconRose size={30} strokeWidth={1.5} />
      <span className="hero-mark__word">{HERO.brand}</span>
    </p>
  )
}

/** The numeral and its unit in two fixed-width boxes, so a changing tick never moves anything. */
function Clock({ tick }: { tick: Tick }) {
  return (
    <p className="hero-clock" aria-hidden="true">
      <span className="hero-clock__n num">{tick.n}</span>
      <span className="hero-clock__unit">{tickUnit(tick)}</span>
    </p>
  )
}

function Survey() {
  return (
    <>
      <p className="hero-line">
        <span className="hero-line__nowrap">{HERO.survey}</span> <strong className="hero-line__money num">{HERO.money}</strong>
      </p>
      <p className="hero-source">{HERO.source}</p>
    </>
  )
}

function Answer() {
  return <p className="hero-line hero-line--answer">{HERO.answer}</p>
}

function HeroPromise({ caseHref }: { caseHref: string }) {
  return (
    <>
      <h1 id="hero-title" className="hero-title">
        {HERO.title}
      </h1>
      <div className="hero-actions">
        <Link to={caseHref} className="btn btn--lg btn--on-dark btn--primary">
          {HERO.openCase}
        </Link>
        <Link to="/analyze" className="btn btn--lg btn--on-dark">
          {HERO.analyze}
        </Link>
      </div>
    </>
  )
}

function ScrollHero({ caseHref }: { caseHref: string }) {
  const track = useRef<HTMLDivElement>(null)
  const { scrollYProgress: p, scrollY } = useScroll({ target: track, offset: ['start start', 'end end'] })

  // The clock: progress maps linearly onto the tick list; floor keeps each tick for an equal stretch.
  const tickAt = (v: number) => {
    const t = (v - CLOCK_START) / (CLOCK_END - CLOCK_START)
    return Math.max(0, Math.min(COUNTDOWN.length - 1, Math.floor(t * COUNTDOWN.length)))
  }
  const [tick, setTick] = useState(() => tickAt(p.get()))

  // Beat 2: the survey line stays through the first half of the countdown; the Tea Rose line arrives late, as the clock nears a minute.
  const surveyOpacity = useTransform(p, [0.3, 0.36], [1, 0])
  const answerOpacity = useTransform(p, [0.4, 0.48], [0, 1])
  const answerY = useTransform(p, [0.4, 0.48], [12, 0])

  // Beat 3: the clock recedes, the headline settles.
  const figOpacity = useTransform(p, [0.72, 0.8], [1, 0])
  const figScale = useTransform(p, [0.72, 0.8], [1, 0.96])
  const figY = useTransform(p, [0.72, 0.8], [0, -24])
  const promiseOpacity = useTransform(p, [0.76, 0.86], [0, 1])
  const promiseY = useTransform(p, [0.76, 0.86], [24, 0])
  // Function form on purpose: a range that starts at 0 is hardware-accelerated onto a ScrollTimeline,
  // which reads as 0 (hidden) at the very top of the page.
  const hintOpacity = useTransform(p, (v) => 1 - Math.min(1, Math.max(0, v / 0.04)))

  // Invisible layers must not catch clicks; pills become live once the promise is mostly in.
  const [promiseLive, setPromiseLive] = useState(false)
  useMotionValueEvent(p, 'change', (v) => {
    setTick(tickAt(v))
    setPromiseLive(v >= 0.8)
  })

  // While the black stage is under the nav, the shell's light scroll-edge fade would paint a gray
  // haze over it; home.css hides that fade for as long as this flag is set.
  useEffect(() => {
    const root = document.documentElement
    const sync = () => {
      const el = track.current
      if (el && el.getBoundingClientRect().bottom > 88) root.setAttribute('data-hero-under-nav', '')
      else root.removeAttribute('data-hero-under-nav')
    }
    sync()
    const off = scrollY.on('change', sync)
    return () => {
      off()
      root.removeAttribute('data-hero-under-nav')
    }
  }, [scrollY])

  // Keyboard: tabbing into the pills while the promise is still hidden scrolls to the last beat.
  function onPromiseFocus(e: FocusEvent<HTMLDivElement>) {
    const el = track.current
    if (!el || p.get() >= 0.86 || !e.currentTarget.contains(e.target)) return
    const top = el.getBoundingClientRect().top + window.scrollY
    const travel = el.offsetHeight - window.innerHeight
    window.scrollTo({ top: top + travel * 0.9, behavior: 'auto' })
  }

  return (
    <section className="band hero-black hero-pin" aria-labelledby="hero-title">
      <p className="sr-only">
        {HERO.sr} {HERO.source}
      </p>
      <div ref={track} className="hero-pin__track">
        <div className="hero-pin__stage">
          <div className="hero-pin__content">
            <Mark />
            <div className="hero-pin__beats">
              <motion.div
                className="hero-pin__layer hero-pin__figure"
                style={{ opacity: figOpacity, scale: figScale, y: figY }}
                aria-hidden="true"
              >
                <p className="hero-eyebrow">{HERO.eyebrow}</p>
                <Clock tick={COUNTDOWN[tick]} />
                <div className="hero-pin__swap">
                  <motion.div className="hero-pin__line" style={{ opacity: surveyOpacity }}>
                    <Survey />
                  </motion.div>
                  <motion.div className="hero-pin__line" style={{ opacity: answerOpacity, y: answerY }}>
                    <Answer />
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
            </div>
          </div>

          <motion.p className="hero-pin__hint" style={{ opacity: hintOpacity }} aria-hidden="true">
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
    <section className="band hero-black hero-static" aria-labelledby="hero-title">
      <p className="sr-only">
        {HERO.sr} {HERO.source}
      </p>
      <div className="wrap hero-static__beats">
        <Mark />
        <div className="hero-static__beat" aria-hidden="true">
          <p className="hero-eyebrow">{HERO.eyebrow}</p>
          <Clock tick={COUNTDOWN[0]} />
          <div className="hero-pin__line">
            <Survey />
          </div>
        </div>
        <div className="hero-static__beat" aria-hidden="true">
          <Clock tick={COUNTDOWN[COUNTDOWN.length - 1]} />
          <div className="hero-pin__line">
            <Answer />
          </div>
        </div>
        <div className="hero-static__beat">
          <HeroPromise caseHref={caseHref} />
        </div>
      </div>
    </section>
  )
}

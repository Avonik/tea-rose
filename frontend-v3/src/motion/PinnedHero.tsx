import { motion, useMotionValueEvent, useReducedMotion, useScroll, useTransform } from 'motion/react'
import { useRef, useState, type FocusEvent } from 'react'
import { Link } from 'react-router-dom'
import { HERO } from '../content/home'

/**
 * The home hero, pinned to scroll (docs/SITE_STORY.md §1). One progress value, read straight from
 * the scroll position of a ~300vh track, drives three beats:
 *
 *   0.00–0.26  stake    "$15,000 to $100,000" over "Six to eight weeks."
 *   0.26–0.50  turn     the weeks line rolls away, "About one minute." rolls in; the money stays
 *   0.60–0.84  promise  the figure recedes, the headline and the two pills settle
 *   0.84–1.00  hold, then the sticky stage scrolls away with the page
 *
 * Nothing autoplays and nothing captures the wheel: the beats are a pure function of where the
 * reader is, so scrolling back reverses them at any point. Under prefers-reduced-motion the three
 * beats render stacked in normal flow, with no pinning.
 *
 * DOM order equals reading order (stake, turn, promise). The rolling weeks/minute layer is visual
 * only (aria-hidden); the same words exist as text in the copy blocks for assistive tech.
 */
export function PinnedHero({ caseHref }: { caseHref: string }) {
  const reduce = useReducedMotion()
  return reduce ? <StaticHero caseHref={caseHref} /> : <ScrollHero caseHref={caseHref} />
}

function Money() {
  return (
    <p className="hero-pin__money num">
      {HERO.money.from} <span className="hero-pin__to">to</span> {HERO.money.to}
    </p>
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

  // beat 1 → 2: the duration rolls from weeks to a minute, the copy under it cross-fades
  const weeksOpacity = useTransform(p, [0.26, 0.4], [1, 0])
  const weeksY = useTransform(p, [0.26, 0.4], ['0em', '-0.7em'])
  const weeksBlur = useTransform(p, [0.26, 0.4], ['blur(0px)', 'blur(10px)'])
  const minuteOpacity = useTransform(p, [0.34, 0.5], [0, 1])
  const minuteY = useTransform(p, [0.34, 0.5], ['0.7em', '0em'])
  const minuteBlur = useTransform(p, [0.34, 0.5], ['blur(10px)', 'blur(0px)'])
  const stakeOpacity = useTransform(p, [0.24, 0.36], [1, 0])
  const turnOpacity = useTransform(p, [0.38, 0.5], [0, 1])

  // beat 2 → 3: the figure recedes, the promise settles
  const figOpacity = useTransform(p, [0.6, 0.74], [1, 0])
  const figScale = useTransform(p, [0.6, 0.74], [1, 0.94])
  const figY = useTransform(p, [0.6, 0.74], [0, -28])
  const promiseOpacity = useTransform(p, [0.68, 0.84], [0, 1])
  const promiseY = useTransform(p, [0.68, 0.84], [36, 0])
  const hintOpacity = useTransform(p, [0, 0.06], [1, 0])

  // Invisible layers must not catch clicks; pills become live once the promise is mostly in.
  const [beat, setBeat] = useState<1 | 2 | 3>(1)
  useMotionValueEvent(p, 'change', (v) => setBeat(v < 0.37 ? 1 : v < 0.72 ? 2 : 3))

  // Keyboard: tabbing into the pills while the promise is still hidden scrolls to beat 3.
  function onPromiseFocus(e: FocusEvent<HTMLDivElement>) {
    const el = track.current
    if (!el || p.get() >= 0.84 || !e.currentTarget.contains(e.target)) return
    const top = el.getBoundingClientRect().top + window.scrollY
    const travel = el.offsetHeight - window.innerHeight
    window.scrollTo({ top: top + travel * 0.88, behavior: 'auto' })
  }

  return (
    <section className="band band--alt hero-pin" aria-labelledby="hero-title">
      <div ref={track} className="hero-pin__track">
        <div className="hero-pin__stage">
          <motion.div className="hero-pin__layer hero-pin__figure" style={{ opacity: figOpacity, scale: figScale, y: figY }}>
            <p className="eyebrow hero-pin__eyebrow">{HERO.eyebrow}</p>
            <Money />
            <div className="hero-pin__morph t-headline" aria-hidden="true">
              <motion.span className="hero-pin__dur" style={{ opacity: weeksOpacity, y: weeksY, filter: weeksBlur }}>
                {HERO.weeks}
              </motion.span>
              <motion.span className="hero-pin__dur" style={{ opacity: minuteOpacity, y: minuteY, filter: minuteBlur }}>
                {HERO.minute}
              </motion.span>
            </div>
            <div className="hero-pin__lines">
              <motion.div className="hero-pin__line" style={{ opacity: stakeOpacity }}>
                <p className="t-subtitle">
                  <span className="sr-only">{HERO.weeks} </span>
                  {HERO.stake}
                </p>
                <p className="caption tertiary hero-pin__source">{HERO.source}</p>
              </motion.div>
              <motion.div className="hero-pin__line" style={{ opacity: turnOpacity }}>
                <p className="t-subtitle">
                  <span className="sr-only">{HERO.turnSr} </span>
                  {HERO.turn}
                </p>
              </motion.div>
            </div>
          </motion.div>

          <motion.div
            className="hero-pin__layer hero-pin__finale"
            style={{ opacity: promiseOpacity, y: promiseY, pointerEvents: beat === 3 ? 'auto' : 'none' }}
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
      <div className="wrap hero-static__beats">
        <div className="hero-static__beat">
          <p className="eyebrow">{HERO.eyebrow}</p>
          <Money />
          <p className="t-headline">{HERO.weeks}</p>
          <p className="t-subtitle">{HERO.stake}</p>
          <p className="caption tertiary hero-pin__source">{HERO.source}</p>
        </div>
        <div className="hero-static__beat">
          <p className="t-headline">
            <span className="sr-only">With Tea Rose: </span>
            {HERO.minute}
          </p>
          <p className="t-subtitle">{HERO.turn}</p>
        </div>
        <div className="hero-static__beat">
          <HeroPromise caseHref={caseHref} />
        </div>
      </div>
    </section>
  )
}

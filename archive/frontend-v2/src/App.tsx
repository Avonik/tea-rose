import { AnimatePresence, LayoutGroup, motion, useReducedMotion } from 'motion/react'
import { lazy, Suspense, useEffect, useRef, useState } from 'react'
import { BrowserRouter, Link, NavLink, Outlet, Route, Routes, useLocation } from 'react-router-dom'
import { MOCK } from './api'
import { IconMonitor, IconMoon, IconRose, IconSun } from './components/icons'
import { Segmented, StateView } from './components/ui'
import { SectionProvider, useActiveSection, useSections } from './lib/sections'
import { useTheme } from './lib/theme'
import { fade, spring, springQuick } from './motion/springs'
import HomePage from './pages/HomePage'
import './styles/app.css'

const AnalyzePage = lazy(() => import('./pages/AnalyzePage'))
const RunPage = lazy(() => import('./pages/RunPage'))
const CasePage = lazy(() => import('./pages/CasePage'))
const MethodPage = lazy(() => import('./pages/MethodPage'))
const NotFoundPage = lazy(() => import('./pages/NotFoundPage'))

const NAV = [
  { to: '/', label: 'Cases', end: true },
  { to: '/analyze', label: 'Analyze' },
  { to: '/method', label: 'Method' },
]

/** Section chips need to clear the floating nav (12 + 48 + 44 px) before they count as "current". */
const SPY_OFFSET = 150

function useScrolled(threshold = 8) {
  const [scrolled, setScrolled] = useState(false)
  useEffect(() => {
    const on = () => setScrolled(window.scrollY > threshold)
    on()
    window.addEventListener('scroll', on, { passive: true })
    return () => window.removeEventListener('scroll', on)
  }, [threshold])
  return scrolled
}

function MainItems() {
  const reduce = useReducedMotion()
  const { pathname } = useLocation()
  const current = NAV.find((n) => (n.end ? pathname === n.to || pathname.startsWith('/case/') : pathname.startsWith(n.to) || (n.to === '/analyze' && pathname.startsWith('/run/'))))
  return (
    <LayoutGroup id="mainnav">
      <ul className="fnav__items">
        {NAV.map((n) => {
          const on = current?.to === n.to
          return (
            <li key={n.to}>
              <NavLink to={n.to} end={n.end} className="fnav__item pressable" aria-current={on ? 'page' : undefined}>
                {on && <motion.span layoutId="fnav-pill" className="fnav__pill" transition={reduce ? fade : springQuick} aria-hidden="true" />}
                <span className="fnav__label">{n.label}</span>
              </NavLink>
            </li>
          )
        })}
      </ul>
    </LayoutGroup>
  )
}

/** Run and case pages publish their sections; they appear as a second row inside the same glass. */
function SectionChips() {
  const { sections } = useSections()
  const reduce = useReducedMotion()
  const active = useActiveSection(
    sections.map((s) => s.id),
    SPY_OFFSET,
  )
  const rowRef = useRef<HTMLDivElement>(null)

  // Keep the current chip visible inside the chip row (scroll the row, never the page).
  useEffect(() => {
    const row = rowRef.current
    const el = row?.querySelector<HTMLElement>('[aria-current="location"]')
    if (!row || !el) return
    const left = el.offsetLeft - row.clientWidth / 2 + el.offsetWidth / 2
    row.scrollTo({ left, behavior: reduce ? 'auto' : 'smooth' })
  }, [active, reduce])

  return (
    <LayoutGroup id="sectionchips">
      <div className="fnav__sections" ref={rowRef}>
        <ul>
          {sections.map((s) => {
            const on = active === s.id
            return (
              <li key={s.id}>
                <a href={`#${s.id}`} className="fnav__chip pressable" aria-current={on ? 'location' : undefined}>
                  {on && <motion.span layoutId="fnav-chip" className="fnav__chip-pill" transition={reduce ? fade : springQuick} aria-hidden="true" />}
                  <span className="fnav__label">{s.label}</span>
                </a>
              </li>
            )
          })}
        </ul>
      </div>
    </LayoutGroup>
  )
}

/** A floating glass pill. It never spans the viewport; content runs underneath it. */
function FloatingNav() {
  const { sections } = useSections()
  const reduce = useReducedMotion()
  const scrolled = useScrolled()
  const hasSections = sections.length > 1
  return (
    <header className="fnav-wrap no-print">
      <motion.nav
        className="fnav"
        aria-label="Main"
        data-scrolled={scrolled || undefined}
        data-sections={hasSections || undefined}
        layout
        transition={reduce ? fade : spring}
        style={{ borderRadius: 24 }}
      >
        <motion.div className="fnav__row" layout="position" transition={reduce ? fade : spring}>
          <Link to="/" className="fnav__brand pressable" aria-label="Tea Rose, all cases">
            <IconRose size={20} />
          </Link>
          <MainItems />
        </motion.div>
        <AnimatePresence initial={false}>
          {hasSections && (
            <motion.div
              key="sections"
              className="fnav__sections-wrap"
              aria-label="On this page"
              role="navigation"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={reduce ? fade : springQuick}
              layout="position"
            >
              <SectionChips />
            </motion.div>
          )}
        </AnimatePresence>
      </motion.nav>
    </header>
  )
}

/** Scroll-edge effect: a soft blur where content meets the floating nav, only once content is under it. */
function ScrollEdge() {
  const scrolled = useScrolled()
  return <div className="scroll-edge no-print" data-on={scrolled || undefined} aria-hidden="true" />
}

function AppearanceControl() {
  const [theme, setTheme] = useTheme()
  return (
    <Segmented
      size="sm"
      label="Appearance"
      value={theme}
      onChange={setTheme}
      options={[
        { value: 'system', label: 'System', icon: <IconMonitor size={14} />, title: 'Follow the system' },
        { value: 'light', label: 'Light', icon: <IconSun size={14} />, title: 'Light' },
        { value: 'dark', label: 'Dark', icon: <IconMoon size={14} />, title: 'Dark' },
      ]}
    />
  )
}

const BASE_TITLE = 'Tea Rose · Trademark evidence from the taste graph'
const PAGE_TITLE: Record<string, string> = {
  '/': BASE_TITLE,
  '/analyze': 'Analyze a dispute · Tea Rose',
  '/method': 'Method · Tea Rose',
}

function DocumentTitle() {
  const { pathname } = useLocation()
  useEffect(() => {
    if (pathname.startsWith('/run/') || pathname.startsWith('/case/')) return
    document.title = PAGE_TITLE[pathname] ?? 'Page not found · Tea Rose'
  }, [pathname])
  return null
}

function ScrollToTop() {
  const { pathname } = useLocation()
  useEffect(() => {
    window.scrollTo(0, 0)
  }, [pathname])
  return null
}

function Footer() {
  return (
    <footer className="footer no-print">
      <div className="wrap wrap--wide footer__inner">
        <div className="footer__text">
          <p>Tea Rose produces triage evidence, not a litigation survey.</p>
          <p>Taste data by Qloo. Built for the Qloo Agentic Hackathon 2026.</p>
          <p className="footer__links">
            <Link to="/method">How the numbers are made</Link>
            {MOCK && (
              <span className="footer__mock" title="Serving src/mock data; no backend">
                Mock data mode
              </span>
            )}
          </p>
        </div>
        <div className="footer__appearance">
          <span className="footer__label" id="appearance-label">
            Appearance
          </span>
          <AppearanceControl />
        </div>
      </div>
    </footer>
  )
}

function Layout() {
  return (
    <>
      <a href="#main" className="skip-link">
        Skip to content
      </a>
      <ScrollToTop />
      <DocumentTitle />
      <ScrollEdge />
      <FloatingNav />
      <main id="main" tabIndex={-1}>
        <Suspense fallback={<StateView kind="loading" title="Loading" />}>
          <Outlet />
        </Suspense>
      </main>
      <Footer />
    </>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <SectionProvider>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<HomePage />} />
            <Route path="analyze" element={<AnalyzePage />} />
            <Route path="run/:id" element={<RunPage />} />
            <Route path="case/:slug" element={<CasePage />} />
            <Route path="method" element={<MethodPage />} />
            <Route path="*" element={<NotFoundPage />} />
          </Route>
        </Routes>
      </SectionProvider>
    </BrowserRouter>
  )
}

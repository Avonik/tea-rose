import { lazy, Suspense, useEffect, useState } from 'react'
import { BrowserRouter, Link, NavLink, Outlet, Route, Routes, useLocation } from 'react-router-dom'
import { MOCK } from './api'
import { IconRose } from './components/icons'
import { StateView } from './components/ui'
import ShowcasePage from './pages/ShowcasePage'

const AnalyzePage = lazy(() => import('./pages/AnalyzePage'))
const RunPage = lazy(() => import('./pages/RunPage'))
const CasePage = lazy(() => import('./pages/CasePage'))
const MethodPage = lazy(() => import('./pages/MethodPage'))
const NotFoundPage = lazy(() => import('./pages/NotFoundPage'))

function usePrintDisclosures() {
  // Closed <details> hide their content when printed; open the ones marked for print, then restore.
  useEffect(() => {
    let opened: HTMLDetailsElement[] = []
    const before = () => {
      opened = Array.from(document.querySelectorAll<HTMLDetailsElement>('details[data-print-open]:not([open])'))
      opened.forEach((d) => (d.open = true))
    }
    const after = () => {
      opened.forEach((d) => (d.open = false))
      opened = []
    }
    window.addEventListener('beforeprint', before)
    window.addEventListener('afterprint', after)
    return () => {
      window.removeEventListener('beforeprint', before)
      window.removeEventListener('afterprint', after)
    }
  }, [])
}

function Topbar() {
  const [scrolled, setScrolled] = useState(false)
  const { pathname } = useLocation()
  const wide = pathname.startsWith('/run/') || pathname.startsWith('/case/')
  useEffect(() => {
    const on = () => setScrolled(window.scrollY > 4)
    on()
    window.addEventListener('scroll', on, { passive: true })
    return () => window.removeEventListener('scroll', on)
  }, [])
  return (
    <header className="topbar no-print" data-scrolled={scrolled}>
      <div className={`${wide ? 'container-wide' : 'container'} topbar__inner`}>
        <Link to="/" className="brand" aria-label="Tea Rose, home">
          <span className="brand__mark">
            <IconRose size={18} />
          </span>
          <span>
            Tea Rose
          </span>
          {MOCK && (
            <span className="brand__mode" title="Serving src/mock data; no backend">
              Mock
            </span>
          )}
        </Link>
        <nav className="nav" aria-label="Main">
          <NavLink to="/" end>
            Cases
          </NavLink>
          <NavLink to="/analyze">Analyze</NavLink>
          <NavLink to="/method">Method</NavLink>
        </nav>
      </div>
    </header>
  )
}

function ScrollToTop() {
  const { pathname } = useLocation()
  useEffect(() => {
    window.scrollTo(0, 0)
  }, [pathname])
  return null
}

function Layout() {
  usePrintDisclosures()
  return (
    <>
      <a href="#main" className="skip-link">
        Skip to content
      </a>
      <ScrollToTop />
      <Topbar />
      <main id="main" tabIndex={-1}>
        <Suspense fallback={<StateView kind="loading" title="Loading" />}>
          <Outlet />
        </Suspense>
      </main>
      <footer className="footer no-print">
        <div className="container footer__inner">
          <span>Tea Rose · triage evidence, not a litigation survey. Taste data by Qloo.</span>
          <span>
            <Link to="/method">How the numbers are made</Link>
          </span>
        </div>
      </footer>
    </>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<ShowcasePage />} />
          <Route path="analyze" element={<AnalyzePage />} />
          <Route path="run/:id" element={<RunPage />} />
          <Route path="case/:slug" element={<CasePage />} />
          <Route path="method" element={<MethodPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

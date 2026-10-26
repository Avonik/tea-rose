import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'

export interface SectionLink {
  id: string
  label: string
}

interface Ctx {
  sections: SectionLink[]
  setSections: (s: SectionLink[]) => void
}

const SectionContext = createContext<Ctx>({ sections: [], setSections: () => {} })

export function SectionProvider({ children }: { children: ReactNode }) {
  const [sections, setSections] = useState<SectionLink[]>([])
  const value = useMemo(() => ({ sections, setSections }), [sections])
  return <SectionContext.Provider value={value}>{children}</SectionContext.Provider>
}

/** Pages with an in-page index publish it here; the top bar renders it (one material, not two). */
export function useSections() {
  return useContext(SectionContext)
}

export function usePublishSections(sections: SectionLink[]) {
  const { setSections } = useSections()
  const key = sections.map((s) => s.id + s.label).join('|')
  useEffect(() => {
    setSections(sections)
    return () => setSections([])
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, setSections])
}

/** Which of the given section ids is currently the reader's position (scroll spy). */
export function useActiveSection(ids: string[], offset = 96): string | null {
  const [active, setActive] = useState<string | null>(null)
  const key = ids.join('|')
  useEffect(() => {
    if (!ids.length) return
    let raf = 0
    const update = () => {
      raf = 0
      let best: string | null = null
      for (const id of ids) {
        const el = document.getElementById(id)
        if (!el) continue
        if (el.getBoundingClientRect().top - offset <= 0) best = id
      }
      setActive(best ?? ids[0])
    }
    const on = () => {
      if (!raf) raf = requestAnimationFrame(update)
    }
    update()
    window.addEventListener('scroll', on, { passive: true })
    window.addEventListener('resize', on)
    return () => {
      window.removeEventListener('scroll', on)
      window.removeEventListener('resize', on)
      cancelAnimationFrame(raf)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, offset])
  return active
}

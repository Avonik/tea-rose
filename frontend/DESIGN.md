# Tea Rose frontend: design

"Apple keynote, for lawyers." Monochrome chrome, enormous type, generous air, glass and depth; colour
is reserved for data. The reference is apple.com product pages and iOS grouped settings, not a SaaS
dashboard. The apple-design skill (`~/.claude/skills/apple-design/SKILL.md`) is the rulebook for
motion and materials; this file says how it lands here.

Backend contract, data hooks and mocks are unchanged and must not be edited: `src/types.ts`,
`src/api/*`, `src/lib/useLiveRun.ts`, `src/lib/useAsync.ts`, `src/lib/format.ts`, `src/mock/*`,
`src/content/*`, `src/lib/theme.ts`, `src/lib/sections.tsx`, `src/motion/springs.ts`,
`src/motion/Sheet.tsx` (its stylesheet `sheet.css` is restyled).

## Tokens (`src/styles/tokens.css`)

| Role | Light | Dark |
| --- | --- | --- |
| Page / alternating band | `#ffffff` / `#f5f5f7` | `#000000` / `#161617` |
| Grouped surface (`--group`) | `#f5f5f7` on white, `#ffffff` on gray | `#1c1c1e` / `#2c2c2e` |
| Text / secondary / tertiary | `#1d1d1f` / `#6e6e73` / `#86868b` | `#f5f5f7` / `#a1a1a6` / `#6e6e73` |
| Hairline | `rgba(0,0,0,.08)` | `rgba(255,255,255,.12)` |
| Glass | `rgba(255,255,255,.72)` + `saturate(180%) blur(20px)` | `rgba(22,22,23,.72)` |
| Primary pill | `#1d1d1f` on white text | `#f5f5f7` with dark text |
| Link / focus ring | `#0066cc` | `#2997ff` |
| Senior (data only) | `#5e5ce6` | `#7d7aff` |
| Junior (data only) | `#ff9f0a` | `#ffb340` |
| Negative (diverging bars) | `#ff453a` | `#ff6961` |
| Status | amber `#ff9f0a` tint, red `#ff3b30`, green `#30d158`; always icon + label | |

No accent colour anywhere in chrome. The brand mark is the monochrome rose glyph (`IconRose`).
`--group` is set by the band: `.band` gives grouped surfaces the gray tone, `.band--alt` gives them
white, so a group always contrasts with the band it sits on.

Dark mode: `prefers-color-scheme` guarded by `:root:not([data-theme="light"])`, repeated under
`:root[data-theme="dark"]` (the footer's System / Light / Dark control sets `data-theme`).
`prefers-reduced-transparency` turns glass solid; `prefers-contrast: more` raises secondary text,
hairlines and glass to near-solid with a defined edge. Print forces the light palette.

## Type

System stack (`-apple-system … "Segoe UI Variable Display" …`); memo prose, the bottom line, the
hero frame headline, goods quotes and the intake textarea use `ui-serif, "New York", Georgia`.

| Role | Size | Weight / tracking / leading |
| --- | --- | --- |
| `.t-display` | `clamp(3rem, 2rem + 6vw, 7rem)` | 600 / −0.045em / 1.0 |
| `.t-headline` | `clamp(2rem, 1.4rem + 2.6vw, 3.5rem)` | 600 / −0.03em / 1.06 |
| `.t-title` | 1.75rem | 600 / −0.02em |
| `.t-subtitle` | 1.3125rem | 400, secondary colour |
| body | 1.0625rem | leading 1.47 |
| `.caption` / `.eyebrow` | 0.75rem | +0.01em / 600 uppercase +0.1em |
| `.numeral` | `clamp(4.5rem, …, 6rem)` | 600 / −0.04em, tabular |

Everything is in rem; headings use `text-wrap: balance`. Hierarchy is weight + size + leading.

## Layout patterns

- **Floating nav** (`App.tsx`, `styles/app.css`): a centred glass pill, 48 px tall, 12 px from the top,
  never full width. Rose glyph + Cases / Analyze / Method with a sliding selection pill (`layoutId`).
  On run/case pages the pill grows a second row of section chips (published with
  `usePublishSections`, spied with `useActiveSection(ids, 150)`), one material, never two. The active
  chip is scrolled into view inside the row. A `.scroll-edge` blur/gradient appears where content
  passes under the nav instead of a hard divider.
- **Bands**: full-bleed `.band` sections alternating white / `#f5f5f7` (`.band--alt`), padding
  `clamp(5rem, 10vw, 9rem)`. `.wrap` = 61.25rem text width, `.wrap--wide` = 75rem for boards, 22 px
  gutters. `.page-top` clears the floating nav on pages without a hero.
- **Grouped lists** (`.group`, `.group__row`, `.group-label`, `.group__sep`, `--inset`): 18 px radius,
  inset hairlines, chevrons on navigable rows. Used for the case list, parties, resolution, tag menu,
  routing, findings, limitations, appendix, peer tables, regions, method formulas.
- **Cards** only where unavoidable (`.card`, question tiles, device frame): 28 px radius, no border, no
  shadow at rest; links lift 2 px with a soft shadow on hover and scale 0.98 on press.
- **Pills** (`.btn`): gray default, `--primary` black/white, `--link`, `--glass`; `--sm --lg --icon`.
- **Chips** (`.chip`): gray; `aria-pressed` = black. Party identity appears only as a `.dot`
  (`dot--senior`, `dot--junior`) inside chips, gauges, legends and toggles. `LeanChip` uses the dot
  (indigo favours senior, orange favours junior, gray neutral, hollow insufficient data).

## Pages

1. **Home** (`pages/HomePage.tsx`, `styles/home.css`): 92 vh hero on the gray band, display
   headline, two pills, sourced survey-cost caption, then the **device frame**: a glass-rimmed 28 px
   panel with the live preview of the first showcase case (`api.showcase()` → `api.showcaseCase`):
   serif memo headline, factor → lean chips, the symmetric percentile numeral with a horizontal gauge,
   and three tiles (shared-purchaser percentile, fame breadth, geographic concentration). It scales
   0.94 → 1 and fades in with `useScroll` + `useTransform`; a skeleton holds its height while loading.
   Then: three question tiles, the case grouped list, the 8-step "How it works" timeline (Extract, Route,
   Resolve, Fetch, Score, Interpret, Assess, Memo; copy in `content/home.ts`; agent = filled, code =
   outlined with a code glyph, memo = half; progress line springs in on view; vertical on phones),
   and the five limitations.
2. **Analyze** (`pages/AnalyzePage.tsx`, `styles/analyze.css`): gate (lock in a gray circle, 52 px
   input, full-width primary pill, errors drop in from above, lockout countdown, 503 / live-off
   notices, mock hint). Intake: one grouped surface with sample chips, a borderless serif textarea
   (16 rows), and a footer with the character count, Upload and Analyze; drag-over shows a glass
   "Drop to attach" overlay. Runs-left chip, Sign out link, "What happens next" grouped list, privacy
   caption.
3. **Run / Case** (`run/RunView.tsx`, `run/run.css`): a sequence of bands whose tones alternate in
   order; while streaming every band that will exist is reserved with a labelled skeleton, so the
   alternation never flips. The **Preliminary read** card (`PreliminaryRead.tsx`: lean, confidence,
   what it turns on, strongest defence) comes first; on showcase cases a court-reveal row
   (`CourtReveal` in `RunView.tsx`: what the court decided vs what Tea Rose read) follows it. Then Opening (eyebrow doc type · forum, headline, glass toolbar with back link,
   status, data mode and Print memo, summary, claims) + **Bottom line** (`BottomLine.tsx`). Parties
   (`CaseHeader.tsx`: `CaseOpening`, `CaseParties`; two grouped lists with a serif "v.", routing,
   key passages). Who was measured (`ResolutionCard.tsx`). Evidence intro band, then one band per
   analysis (`OverlapPanel`, `BridgingPanel`, `FamePanel`, `ZonePanel`) built on
   `EvidenceKit.tsx`'s `EvidenceSplit`: left column eyebrow / headline question / giant numeral /
   plain reading / notes, right column the chart, full-width detail below. Memo band (`MemoView.tsx`,
   `memo.css`) with `FollowupBox` for live runs; run foot.
   **Trace**: ≥1080 px a floating glass dock bottom-right (380 px, max 60 vh) that collapses into a
   48 px pill "Agent trace · Step n of 8 · … · N Qloo calls"; it opens itself for a live run and folds
   once the run settles unless the reader toggled it. Below 1080 px the trace is `Sheet.tsx`
   (peek/half/full, rises to half once when streaming starts; a tap on the grab area toggles
   peek ↔ half). `TraceAnnouncer` is the single sr-only live region for step changes.
4. **Method** (`pages/MethodPage.tsx`, `styles/method.css`): long-form bands (question tiles with
   mono endpoint chips, "How a number is made" grouped definition list, agent vs code, pre-registered
   evaluation, limitations, About Qloo); sticky mini-TOC at ≥1080 px using `useActiveSection`.
5. **404** (`pages/NotFoundPage.tsx`): centred display headline and a link.

## Data-viz

Gauges (`RankGauge.tsx`) run weakest → #1 left to right with a median tick; fill and marker carry the
party colour, text never does. Peer lists and compare lists are grouped lists with 4 px-radius bars.
Fame is SVG diverging bars (indigo over-index, red under-index, hairline zero and grid) with an HTML
value overlay, a legend and a "Show values as a table" disclosure. The zone map is MapLibre with
single-hue indigo / orange heat ramps and glass layer toggles on the map; the regions list is the
text equivalent. Every chart has `role="img"` + `aria-label` and a list or table equivalent.

## Motion

`src/motion/springs.ts`: `spring` (damping 1, response 0.4) by default, `springQuick` for small UI,
`springSlow` for numbers and gauges, `springSheet` only after a flick. `useReducedMotion()` swaps
every spring for the `fade` cross-fade. Pointer-down feedback (scale 0.97, 100 ms) on every
pressable (`.pressable`, `.btn`, `button.chip`). Sliding selection pills via `layoutId` (nav, section
chips, segmented control). Arrivals use `AnimatePresence mode="popLayout"` inside reserved slots;
`AnimatedNumber` springs from the value currently shown. Disclosures animate `height: auto`; nothing
else animates layout. Nothing locks input.

## Accessibility and print

44 px targets on coarse pointers (`--target`), 2 px link-blue focus rings, labels on every input,
chart text equivalents, sr-only live region for run steps. `styles/print.css` hides the nav,
scroll edge, toolbar, dock, sheet, follow-up and footer, prints on the light palette, expands
disclosures through their print-only copy, and starts the memo band on a new page.

## File map

| Area | Files |
| --- | --- |
| Shell | `App.tsx`, `main.tsx`, `index.css`, `styles/tokens.css`, `styles/base.css`, `styles/ui.css`, `styles/app.css`, `styles/print.css`, `components/ui.tsx`, `components/icons.tsx` |
| Motion | `motion/springs.ts` (kept), `motion/Sheet.tsx` (kept) + `motion/sheet.css`, `motion/Reveal.tsx`, `motion/AnimatedNumber.tsx` |
| Pages | `pages/HomePage.tsx` + `styles/home.css`, `pages/AnalyzePage.tsx` + `styles/analyze.css`, `pages/MethodPage.tsx` + `styles/method.css`, `pages/NotFoundPage.tsx`, `pages/RunPage.tsx`, `pages/CasePage.tsx` |
| Run | `run/RunView.tsx`, `run/CaseHeader.tsx`, `run/BottomLine.tsx`, `run/ResolutionCard.tsx`, `run/TracePanel.tsx` + `run/trace.css`, `run/run.css` |
| Evidence | `run/EvidenceKit.tsx`, `run/OverlapPanel.tsx`, `run/RankGauge.tsx`, `run/BridgingPanel.tsx`, `run/FamePanel.tsx`, `run/ZonePanel.tsx`, `run/ZoneMap.tsx`, `run/evidence.css` |
| Memo | `run/MemoView.tsx`, `run/FollowupBox.tsx`, `run/memo.css` |

Component props are unchanged for the evidence panels, `MemoView`, `FollowupBox`, `BottomLine` and
`ResolutionCard`. `TracePanel` gains `onCollapse`; `traceProgress`, `Stepper` and `TraceAnnouncer`
are exported from it. `CaseHeader.tsx` now exports `CaseOpening` (default) and `CaseParties`.

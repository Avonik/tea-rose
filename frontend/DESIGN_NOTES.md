# Tea Rose frontend: design notes

Source: the apple-design skill (github.com/emilkowalski/skills, `skills/apple-design/SKILL.md`,
a single file with no referenced sub-files), plus the dataviz method for charts. These rules bind
every later change. When a rule and a shortcut disagree, the rule wins.

## Rules adopted from apple-design

1. **Response first.** Feedback on pointer-down, never only on release: every pressable gets
   `:active { transform: scale(.97) }` with a 100 ms ease-out. No artificial delays, debounces or
   "loading" timers on the input path.
2. **Behavior over animation.** Motion is critically damped (no overshoot) by default. On the web,
   without a spring library, the house curve `--ease-out: cubic-bezier(.2,.8,.2,1)` at 200–350 ms
   approximates a damping-1.0 spring with response ≈0.3 s. Bounce is reserved for momentum
   gestures, which this product does not have, so nothing bounces.
3. **Interruptible.** Only `transform`/`opacity` animate; nothing locks input during a transition.
   Disclosures and panels can be toggled again mid-motion.
4. **Spatial consistency.** Things leave the way they came. New trace events enter from below
   (the direction the list grows); menus and disclosures open from their trigger.
5. **Materials encode hierarchy.** The top bar is a translucent layer
   (`backdrop-filter: blur(20px) saturate(180%)`) with content scrolling underneath, and a soft
   scroll-edge fade instead of a hard 1 px divider. Never stack a translucent surface on another.
   Text over material is slightly heavier for vibrancy.
6. **Typography.** System font first (`system-ui`/SF Pro). Tracking is size-specific: display
   −0.022 em, titles −0.012 em, body 0, small caps/captions +0.01–0.04 em. Leading tracks size
   inversely (display 1.05, titles 1.2, body 1.5). Hierarchy from weight + size + leading as a
   set. All sizes and spacing in `rem` so user text size scales the layout. The memo uses the
   platform serif (`ui-serif`, New York on Apple) because it is a document, not chrome.
7. **Reduced motion / transparency / contrast** are three separate signals and all three are
   honoured: motion becomes cross-fades, translucency becomes solid, high contrast gets solid
   backgrounds and defined borders.
8. **Principles as names to reason with.** Purpose (show the evidence, cut decoration), Agency
   (the user can expand every tool call and query; nothing hidden), Responsibility (the
   "What this cannot tell you" box is never optional), Familiarity (tables, chips, disclosure
   triangles behave like the platform's), Simplicity not minimalism (common path first, raw
   params one level deeper), Craft (every value from the token scale), Delight (calm confidence).
9. **Feedback in four kinds**: status (trace progress), completion (memo ready), warning (amber,
   always icon + label), error (inline, specific, with a way out). Validate inline.
10. **Wayfinding.** Every page answers where am I, where can I go, how do I get out: a persistent
    nav with specific labels ("Cases", "Analyze", "Method"), an in-page section index on runs,
    and every error offers a next step.
11. **Grouping & mapping.** Controls sit next to what they change (map layer toggles on the map,
    follow-up box under the memo it rewrites).

## Data-viz rules (dataviz skill)

- Identity colors are categorical slots 1 and 2, validated with the skill's script (light and
  dark, CVD ΔE ≥ 24): **senior = blue** `#2a78d6` / dark `#3987e5`, **junior = orange**
  `#eb6834` / dark `#d95926`. Color follows the party everywhere (gauges, peer tables, map).
- Fame bars are polarity data: diverging **blue (over-indexes) ↔ red (under-indexes)** around a
  gray zero line. Heatmaps are sequential: senior uses a single-hue blue ramp, junior orange.
- Text never wears the series color; values use text tokens next to a colored mark.
- Bars ≤ 24 px, 4 px rounded data-end, square at baseline; hairline recessive grid; selective
  direct labels; per-bar hover tooltip; every chart has a table/text equivalent.
- Status colors (warning amber, error red) are reserved for status and always ship with an icon
  and a label.
- The brand rose (`--accent`) is chrome only (links, primary button, focus ring); it never
  encodes data.

## Tokens (src/styles/tokens.css)

| Group | Values |
| --- | --- |
| Spacing | 4 px grid in rem: `--s-1` .25rem … `--s-12` 6rem |
| Radius | 8 / 12 / 18 / 26 px (`--r-sm` … `--r-xl`), pills 999 px |
| Type | `--fs-caption` .8125rem, `--fs-body` 1rem, `--fs-title3` 1.25rem, `--fs-title2` 1.625rem, `--fs-title1` 2.25rem, `--fs-display` clamp(2.25rem, 5.4vw, 4rem) |
| Motion | `--ease-out`, `--dur-1` 120 ms, `--dur-2` 220 ms, `--dur-3` 340 ms |
| Surfaces | `--bg`, `--surface`, `--surface-2`, `--material` (translucent), `--separator` |

## Components and where they live

- `src/components/ui.tsx`: Button, Chip, LeanChip, Badge, Card, Meter, Spinner, Skeleton,
  StateView (loading / empty / error with retry).
- `src/run/*`: RunView and its panels (Trace, CaseHeader, Resolution, Overlap, Bridging, Fame,
  Zone (lazy, MapLibre), Memo, Followup).
- Print: `src/styles/print.css` hides chrome, trace and map controls, opens all disclosures and
  keeps charts. Use the browser's Print → Save as PDF.

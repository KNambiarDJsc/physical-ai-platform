# Design: Precision Industrial

The platform is engineering software for robotics and laboratory teams. It should read like a carefully built
instrument: dense, quiet, exact. Interaction references are Linear (application shell, density, keyboard),
Foxglove and Rerun (synchronized multimodal workspaces), Sentry (failure triage), n8n (workflow canvases) and
Vercel (onboarding and environments). They are references for interaction quality, not templates to copy.

This file is the contract for every screen. When a screen and this file disagree, fix one of them in the same
change.

## 1. Honesty rules come first

The product invariants in `CLAUDE.md` outrank every visual rule here.

- A number on screen comes from stored data or engine output. No decorative charts, sample values or
  placeholder metrics, ever, including on empty states and marketing pages.
- A module that does not exist is not in the navigation. A capability that is partly built says what is
  missing on the page itself (see the Integrations page "Not integrated yet" panel).
- Simulated or synthetic evidence carries its label everywhere it appears.
- Unknown is a result and gets its own colour; it is never folded into success or into warning.
- Concept imagery (renders, mock-ups) never appears inside the application.

## 2. Colour tokens

Defined once in `apps/web/src/app/globals.css` (`@theme`), used through Tailwind utilities
(`bg-panel`, `text-muted`, `border-line`, …). Never write a hex value in a component.

| Token | Role | Dark | Light |
|---|---|---|---|
| `bg` | Canvas | `#111418` | `#F5F6F8` |
| `panel` | Panels, sidebar, tables | `#191D23` | `#FFFFFF` |
| `sunken` | Hover rows, wells, code | `#1F242B` | `#EEF0F3` |
| `line` | Borders and dividers | `#2B313A` | `#DDE1E6` |
| `ink` | Primary text | `#E8EDF2` | `#111418` |
| `muted` | Secondary text | `#9BA8B7` | `#525D6A` |
| `faint` | Tertiary text, axis labels | `#838E9C` | `#626C78` |
| `accent` | Interactive: links, focus, selection, primary action | `#6699E8` | `#2F64C7` |
| `on-accent` | Text on an accent fill | `#0B1322` | `#FFFFFF` |
| `ok` | Verified success, supported success | `#47B88A` | `#1D7A54` |
| `warn` | Contradiction, warnings, simulated-evidence label | `#E1B45C` | `#946000` |
| `bad` | Verified failure, regression, errors | `#E06C75` | `#BF3540` |
| `unknown` | Unknown, insufficient evidence, reported only | `#A9AEDB` | `#545A9E` |

Each semantic colour has a `-soft` background (badges, notices). Dark is the default; light follows the
operating system or the theme switch in the top bar. All text tokens meet WCAG AA (4.5:1) on `bg`, `panel` and `sunken`, and on their own `-soft` backgrounds (checked by computing the ratios, not by eye).

Semantic colours are reserved for states. They are not used for decoration, section headers or icons that do
not carry a state.

## 3. Typography

- **Geist Sans** for the interface, **Geist Mono** for identifiers, digests, measurements, commands and logs.
  Both are bundled (`geist` package), not fetched at run time.
- Base size 13–14 px. Page title 15 px semibold. No display sizes inside the application.
- Numbers that line up in columns use `.num` (mono, tabular numerals).
- Sentence case for every label, heading and button. Upper case only for short status tags
  (`PHYSICAL EVIDENCE`).

## 4. Spacing, shape, elevation

- 4 px grid. Panel padding 16 px; table cells 6 × 8 px; sidebar items 28 px tall.
- Radius: 6 px on panels and inputs, 4 px on badges and buttons. No pill-shaped containers.
- Elevation is a 1 px border. Shadows only on overlays (command palette, menus).
- Density over whitespace: an engineer should see a full comparison without scrolling on a 1280 × 720 screen.

## 5. Application shell

- **Left sidebar**: grouped navigation (Release intelligence, Operations, Workspace). Items are real pages
  only. Active item: `sunken` background and `ink` text with an accent bar, not a coloured block.
- **Top bar**: breadcrumb (workspace / page / entity), command palette trigger (`Ctrl K` / `⌘K`), theme switch,
  signed-in identity. Height 44 px.
- **Content**: page header (title, one-line description, actions on the right), then panels. Width is fluid;
  tables scroll inside their panel, never the page sideways.
- **Command palette**: navigation to every page; later, entities (projects, evaluations). Keyboard first:
  arrow keys, Enter, Escape.

The Workbench (instruments left, the run centre, inspector right, timeline bottom, every pane resizable by pointer
and keyboard) uses the same shell. Its 3D viewport and engineering assistant are not built and are not suggested.

## 6. Interaction model per module

Each module gets the pattern that fits its job, not a grid of cards.

| Module | Pattern | Status |
|---|---|---|
| Release intelligence | Baseline-versus-candidate comparison, drill-down to episodes | Built |
| Verification | Reported vs verified table across evaluations | Built |
| Incidents | Engine incident list with explanation | Built |
| Evidence | Content-addressed file list with usage | Built |
| Fleet | Robot × release outcome counts | Built (from uploaded evidence, not live) |
| Integrations | API surface, credentials, engine pin, what is not built | Built |
| Hardware Hub (devices) | Device tree and capability inspector, live reads; structured values as tables with freshness badges | Built (WoT/LabThings adapter; ROS observer) |
| Workflows | Template form today; node canvas with properties inspector later | Built (templates and definitions; no canvas) |
| Agents | Tool permissions, configuration, execution traces | Not built |
| Workbench | Instruments, observed robots, run, inspector, timeline; resizable | Built (no 3D viewport, no assistant panel) |
| Proposed experiments | Table on the Workflows page; engineers approve or reject | Built (proposals come from people or the tool layer) |
| Experiments / simulation | Viewport, scenario controls, synchronized telemetry | Not built |
| Datasets, policies, deployments | Episode browser, version history, approvals | Not built |

## 6a. Observations

Observed values are shown as they were received: a state word (fresh, stale, never, missing, latched, not sampled)
always as text in a badge, the age with its unit, and "—" for no value. A required topic that is missing or silent is a
problem (red); the same word on an optional one is not. Identifying columns come first (name, topic, frame, service),
then the state. Wide tables scroll inside a focusable, labelled region. A replayed snapshot says so in its environment
name and in its connectivity record; nothing pretends to be live.

## 7. Data visualization

- Draw only what the engine computed: intervals, counts, rates. The frontend computes no statistic.
- Every chart states its basis: n, interval level, evidence class.
- Axes start at zero for rates; percentages on a 0–100 % axis.
- One accent colour for the measured series; semantic colours only where the mark is a state.
- Charts carry an accessible name; the same numbers are also in a table.

## 8. States

Every data view implements four states: loading (short text, no spinners on fast views), empty (what is
missing and the next action), error (what failed, in the user's terms, and how to retry), success. Signed-out
visitors see the sign-in prompt, never data.

## 9. Writing

- Plain, specific, engineering register. Say what the system measured, not what it "thinks".
- Numbers carry their basis: "32 of 150 episodes", "95 % interval".
- Timestamps: one format, `YYYY-MM-DD HH:mm` in local time (`<Time>` in `ui.tsx`), the exact ISO instant in the
  tooltip. Never `toLocaleString`, whose output changes with the browser locale.
- No marketing language inside the application. No exclamation marks.
- Name things consistently: release, evidence, mapping, evaluation, episode, verdict, incident.

## 10. Motion

Transitions of 120–160 ms on hover and focus only. No entrance animations, no animated charts, no skeleton
shimmer. Respect `prefers-reduced-motion`.

## 11. Accessibility

- Keyboard reachable everything; visible focus ring in `accent`.
- Landmarks: `nav[aria-label=Main]`, one `main`, one `h1` per page.
- Colour is never the only signal: badges carry text.
- Gate: `e2e/a11y.spec.ts` runs axe-core (WCAG 2.0/2.1/2.2 A and AA) on every page in both themes against real
  data, and checks the command palette by keyboard. A new page is added to that list in the same change.
- Visible text is part of every accessible name (WCAG 2.5.3): no `aria-label` that replaces a visible label.
- Dialogs keep focus inside while open and return it to the opener on close.

## 12. Anti-patterns (reject in review)

Purple or blue gradients, glass effects, glowing borders, nested rounded cards, large hero headings inside the
app, decorative charts or fake data, generic robot illustrations, marketing copy, a chatbot that takes over the
page, navigation entries for unbuilt modules, more than one accent colour.

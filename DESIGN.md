# Design: Physical AI Studio

The platform is engineering software for robotics and laboratory teams. Its operating surface is an instrument desk:
dense, quiet and exact, with one dominant viewport and evidence kept beside the selected run. The release and report
surfaces keep a reading-first layout. Interaction references include Linear, Foxglove, Rerun, Sentry, n8n and Vercel;
they inform interaction quality, not a visual template to copy.

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
| `bg` | Canvas | `#0B1016` | `#F2F1ED` |
| `panel` | Panels, tables | `#131B24` | `#FFFFFF` |
| `sunken` | Hover rows, wells, code | `#1B2732` | `#EEF0F3` |
| `line` | Borders and dividers | `#34414D` | `#DDE1E6` |
| `ink` | Primary text | `#EDF3F4` | `#0B1016` |
| `muted` | Secondary text | `#A2B1BB` | `#525D6A` |
| `faint` | Tertiary text, axis labels | `#99A9B4` | `#626C78` |
| `accent` | Interactive: links, focus, selection, primary action | `#89D7DB` | `#16666B` |
| `on-accent` | Text on an accent fill | `#0B1322` | `#FFFFFF` |
| `ok` | Verified success, supported success | `#C6DE77` | `#1D7A54` |
| `warn` | Contradiction, warnings, simulated-evidence label | `#E1B45C` | `#946000` |
| `bad` | Verified failure, regression, errors | `#EF928B` | `#BF3540` |
| `unknown` | Unknown, insufficient evidence, reported only | `#A9AEDB` | `#545A9E` |

Two overlay tokens tint the surface beneath them for interaction: `hover` (dark: white 6 %, light: ink 5 %) and
`selected` (dark: white 10 %, light: ink 8 %). They never carry text on their own. Semantic colours are reserved for
states, not decoration. Theme selection can follow the operating system or be changed in the header.

## 3. Typography

- **Geist Sans** for the interface, **Geist Mono** for identifiers, digests, measurements, commands and logs.
  Both are bundled (`geist` package), not fetched at run time.
- Base size 13–14 px. Page title 15 px semibold. No display sizes inside the application.
- Numbers that line up in columns use `.num` (mono, tabular numerals).
- Sentence case for every label, heading and button. Upper case only for short status tags
  (`PHYSICAL EVIDENCE`).

## 4. Spacing, shape, elevation

- 4 px grid. Page padding is 16–28 px; dense workspace panels use compact internal spacing.
- Radius: 6 px on panels and inputs, 4 px on badges and buttons. No pill-shaped containers.
- Elevation is a 1 px border. Shadows only on overlays (command palette, menus).
- Keep the scene and evidence visible together at workstation widths; below that, preserve access by stacking panels
  without page-level horizontal scrolling.

## 5. Application shell

- **Primary navigation**: one compact, 56 px header with Projects, Studio, Runs, Integrations and Settings. On narrow
  screens, the destinations move to a horizontally scrollable row beneath the brand and account controls.
- **Header controls**: the page finder (`Ctrl K` / `⌘K`), theme switch and signed-in identity. The page finder reaches
  every existing route, including detailed pages that do not fit in the five primary destinations. There is no second
  breadcrumb bar.
- **Content**: page header (title, one-line description, actions on the right), then panels. Width is fluid; tables
  scroll inside their labelled region, never the page sideways.
- **Page finder**: keyboard first; arrow keys, Enter and Escape. It searches the real destinations and pages only.

The Workbench and Digital twin are full-height instrument desks beneath the header. Studio mode controls switch among
Explore, Execute and Investigate. Sources and evidence flank a flexible scene or run view; both side panels can be
collapsed, and split handles support pointer and keyboard resizing. The twin defaults to 230 px for sources, 320 px
for evidence and a 164 px playback timeline. The Workbench timeline defaults to 145 px. On small screens the panes
stack so measurements remain reachable without widening the page.

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
| Workbench | Instruments, observed robots, run, inspector, timeline; resizable | Built |
| Digital twin | Model viewport, mode badge, MCAP playback, evidence events, inspector, assistant | Built (recordings and read-only observers; no simulator connector yet) |
| Proposed experiments | Table on the Workflows page; engineers approve or reject | Built (proposals come from people or the tool layer) |
| Experiments / simulation | Guided journey: environment and scenario from the host's own listing, setups as a comparison table, approval of one exact checksum, live trial progress, results beside the Digital twin | Built (Experiment Studio, `/experiments`); a viewport with scenario controls inside the twin is not built |
| Datasets, policies, deployments | Episode browser, version history, approvals | Not built |

## 6a. Observations

Observed values are shown as they were received: a state word (fresh, stale, never, missing, latched, not sampled)
always as text in a badge, the age with its unit, and "—" for no value. A required topic that is missing or silent is a
problem (red); the same word on an optional one is not. Identifying columns come first (name, topic, frame, service),
then the state. Wide tables scroll inside a focusable, labelled region. A replayed snapshot says so in its environment
name and in its connectivity record; nothing pretends to be live.

## 6b. Digital twin
The mode is always stated, as a badge with its reason: Recorded (a recording, or an observer replaying a snapshot, whatever
kind of environment it sits in), Simulated, Live (a physical robot's graph, read-only) or Disconnected (the model does not
move and says so; it is never left at a stale pose). The 3D view is never the only carrier of information: the same
values are in the readout, the joint table and the event list; the view has an accessible name and a text equivalent.
Events carry their rule and sit on the timeline by severity (info, warning, problem); the engine's verdict is shown
beside them and is never derived from them. A joint the recording holds constant is drawn constant, with a warning.
The assistant's answers are findings with evidence ids and a "not known" list, never free prose.

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

Motion confirms a change; it never decorates. The approach follows fluid functionalism (fluidfunctionalism.com):
a small set of speeds, and the bigger the thing that moves, the slower it is. Durations come from the tokens in
`globals.css`, never from a hand-written number.

| Tier | Token | Use |
|---|---|---|
| fast | `--dur-fast` 80 ms | hover, focus, press, colour changes |
| moderate | `--dur-moderate` 160 ms | route content, menus, panels, a state changing by itself |
| slow | `--dur-slow` 240 ms | dialogs and the command palette, with a slight settle (`--ease-settle`) |

- Animate `opacity` and `transform` only, never `width`, `height`, `top` or `left`.
- Route content fades in (`.reveal`), with no rise: a page is not an object that moves. A dialog rises 6 px and
  fades (`.dialog-enter`). A badge fades its colour when a run finishes by itself (`.state-fade`).
- A press is an inset shadow, not a scale.
- Exits are quicker than entrances. Not built yet: the command palette closes instantly; an exit needs a deferred
  unmount that keeps focus return correct.
- Reduced motion means fewer and gentler, not none: movement and the route fade stop; colour fades and a dialog's
  short fade stay (`prefers-reduced-motion`).
- Still not allowed: animated charts, skeleton shimmer, looping or attention-seeking animation, anything that
  delays reading a number.
- Hover and selection tint with the overlay tokens `hover` and `selected`, so they read the same on every surface.

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

## 6c. Experiment Studio

The page is a journey, not a dashboard: Experiments list (with what waits for a decision) → configure → one
experiment (its setup in words, its runs) → one run (review, progress, results). The state is in the URL, so every
step has a link and the browser's Back works. A stage rail (Configured, Approved, Run, Results) says where a run is.

- Words before identifiers: parameters and measurements lose their unit suffix (`speed_mps` is "Speed (m/s)"); people
  are shown by name, never by their identity provider's label; the checksum and the stored specification sit under
  "Technical details".
- The setups are columns of one table, so what differs is visible at a glance and is listed first; what is the same
  in every setup is kept as a shared condition by the page, not by the user.
- Every control works for the person looking at it: a requester who may not approve their own run sees why, not a
  disabled button; a viewer sees no decision controls and is told who decides.
- Verdicts are the engine's; the page shows counts and the host's raw values per setup and says it is not a
  statistical comparison. Simulated evidence is labelled wherever a result appears, including in the twin.
- Errors say what happened and offer the way forward (reload, check again, make a changed version, open the Hardware Hub).

## 6d. Laboratory experiment journey and Agent

**Lab experiment** (`/journey`) is a guide, not a new module. Six numbered steps (discover, configure, request and approve,
inspect the runs, investigate, export), each opening the page where the work is done. A step is "Done" only from stored
data (devices discovered, both procedures present, an approved request, a satisfied and a violated run, an agent session);
nothing is ticked by hand. The tolerance appears in words beside every procedure ("50 µL, accepted within ±2 %"), and the
simulated fault is a labelled badge. The page says first that nothing physical is involved.

**Agent** (`/agent`) shows what is configured before it offers a question box: the model (or that none is set and what
still works), the limits for today and per session, and that the agent is read-only. An answer says who wrote it ("written
by a language model", or "answered by a fixed tool call: no model") and is followed by the cost and a collapsed trace with
digests. A drafted follow-up is a card labelled "drafted, not filed" with one explicit button; it says that nothing runs
until someone else approves. Viewers read; asking needs the engineer role and the page says why. Every state is covered:
not configured, no runner, running, failed, interrupted, stopped by a limit, answered without citing.


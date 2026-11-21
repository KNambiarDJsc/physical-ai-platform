# Design audit, 2026-11-21 (Impeccable `audit`, web)

Method: Impeccable 4.10.0's audit playbook (`.claude/skills/impeccable/reference/audit.md`), run on its documented
"launcher unavailable" path (D-025: its native detector is not installed), so the deterministic part is our own:
axe-core 4.14 in the browser on every page in both themes against real data (`apps/web/e2e/a11y.spec.ts`), computed
WCAG contrast ratios for every token pair, a source scan, and screenshots at 1280 px and 390 px. DESIGN.md is the
reference; nothing here overrides it.

## Audit health score

| # | Dimension | Found | After fixes | Key finding |
|---|---|---|---|---|
| 1 | Accessibility | 2 | 3 | Label-in-name failure on every page (fixed); palette let Tab escape (fixed); no skip link (open) |
| 2 | Performance | 3 | 3 | Fleet fetches up to 2,000 episodes in the browser to count them |
| 3 | Theming | 4 | 4 | Tokens everywhere; one scrim uses `bg-black/40` |
| 4 | Responsive design | 3 | 3 | No horizontal page scroll at 390 px; nav targets 28 px (meets 24 px AA, under 44 px) |
| 5 | Implementation integrity | 2 | 3 | Three different timestamp formats (fixed) |
| | **Total** | **14/20 (Good)** | **16/20 (Good)** | |

**Implementation integrity verdict: pass.** One token system, one accent, semantic colours only on states, no
decorative charts or invented figures, no navigation to unbuilt modules. The drift found was in details
(timestamps, an accessible name), not in the system.

## Findings

| Sev | Finding | Location | Standard | Status |
|---|---|---|---|---|
| P1 | "Go to… Ctrl K" button's accessible name ("Open command palette") did not contain its visible text; axe `label-content-name-mismatch` on all 11 pages | `AppShell.tsx` TopBar | WCAG 2.5.3 | Fixed: visible text is the name |
| P1 | Command palette: Tab moved focus to the page behind the modal; closing did not return focus | `AppShell.tsx` CommandPalette | WCAG 2.4.3, 2.4.11 | Fixed; covered by a keyboard test |
| P2 | Empty-result message was a non-option child of `role=listbox` | `AppShell.tsx` CommandPalette | ARIA 1.2 | Fixed |
| P2 | Timestamps rendered three ways (`toLocaleString`, `toLocaleDateString`, locale-dependent) | project page, Verification, Evidence, Integrations | DESIGN.md §9 | Fixed: one `<Time>` component, `YYYY-MM-DD HH:mm`, ISO in tooltip |
| P2 | No "skip to content" link: keyboard users pass ~10 navigation links on every page | `AppShell.tsx` | WCAG 2.4.1 (landmarks satisfy it formally) | Open |
| P2 | Fleet counts episodes by downloading up to 2,000 rows into the browser | `Modules.tsx` FleetView | Performance | Open: needs an API aggregate |
| P3 | `echarts` is a dependency but unused | `apps/web/package.json` | Bundle hygiene | Open: kept for Workbench telemetry |
| P3 | Project page title repeats the breadcrumb | project page | Consistency | Open |
| P3 | Modal scrim colour is not a token | `AppShell.tsx` | Theming | Open |

Computed contrast: every text token is at least 4.5:1 on `bg`, `panel` and `sunken` and on its own `-soft`
background in both themes (the first `faint` value failed on `sunken` and was corrected before this audit).

## Positive findings

Visible focus ring everywhere; landmarks and one `h1` per page; badges carry text, never colour alone; tables
scroll inside their panels; reduced motion respected; dark and light both pass axe with zero violations.

# Taste review — Physical AI Studio app

## Brief and product idea

This is the existing authenticated engineering application, not a marketing site. Its material is a recorded robotics or
laboratory run: timestamps, measurements, artifacts, identity, approval state and the OpenMHS verdict. Missing evidence
remains unknown; simulation remains labelled.

Taste dealt three directions: `product-performs`, `quiet-instrument` and `type-only-statement`. I chose
`product-performs` because the actual interface is the strongest truthful proof. The sentence is: **on this page, a
time-indexed robot event becomes an investigation bench beside the engine verdict.** A telemetry-only competitor might
show the same event, but not the platform’s stored criterion, run identity and engine-owned result together. The live
interaction is to select a recorded event, inspect the evidence, and explicitly start an evidence-cited investigation.

## Changes

- The header is a wordmark plus five plain text destinations; detailed pages remain in the keyboard page finder.
- Page titles and supporting text use a more decisive, fluid scale. Workspace page padding now responds to viewport width.
- Projects is an API-backed organization/project index, with create forms revealed only on request. No decorative stats or
  placeholder project cards are shown.
- `New project` is the visible primary action for administrators.
- Light mode uses a cool neutral ground and darker secondary text. Signed-in identity truncates before it can push the
  header beyond tablet width.
- The recording viewport, event list, evidence panel and timeline remain actual, working product controls. No visual
  behavior changes the evidence or verdict.

## Render critique

The installed Taste source linter reports **0 FAIL / 0 WARN** for the shell and Projects route. The real-browser inspector
rendered the authenticated Projects page at 1440, 768 and 390 px. The first render exposed an identity-name overflow at
768 px and a tiny organization kicker; both were removed. A follow-up exposed a weak primary action on phone; `New project`
was promoted to the filled action. The final render has no horizontal overflow, no small text, no eyebrow and no first-action
warning.

The final inspector still reports three FAILs and one WARN: no four-picture gallery, no marketing-scale focal image, one
route entrance animation, and no footage. The Taste skill describes itself as a public-page skill and explicitly excludes
app screens. These findings are retained as evidence, not hidden: adding stock photos, generated robot scenes or motion
quotas would make the engineering UI less honest and less useful. The product uses its actual 3D recording view and
stored event evidence where those are relevant.

The project-home screenshots use one temporary, clearly labelled synthetic layout fixture in an isolated disposable test
database. It contains no run evidence. The updated desktop twin screenshot uses the repository’s recorded OpenAMRobot run.

## Verification

- Taste source audit: 0 failures, 0 warnings.
- Web typecheck, lint and production build: passed.
- Playwright a11y and virtual-lab suites: 9 passed (dark and light, keyboard, mobile and lab flows).
- Real recorded-event investigation: 1 passed.
- Taste rendered widths: 1440, 768 and 390 px; no final horizontal overflow.

## Screenshots

- `screenshots/twin-after.png` — updated dark run investigation.
- `screenshots/lab-mobile.png` — mobile Workbench with explicitly labelled simulated evidence.
- `screenshots/project-home-after.jpg` and `screenshots/project-home-mobile.jpg` — API-backed project index with a labelled synthetic QA fixture.

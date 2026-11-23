# Prompt for an OpenAI coding agent (Codex): UI and UX of the Physical AI Platform

Paste everything below the line as the first message. It is self-contained; it also summarises everything built so far,
because the agent should not need the earlier conversations. The earlier general prompt is `CODEX_PROMPT.md`; this one is
about the **interface**.

---

You are taking over the **user interface and user experience** of the **Physical AI Platform** at
`D:\physical-ai-platform` (Windows 11, Git Bash and PowerShell). A previous agent built the platform and a Fraunhofer
demonstration kit in long sessions. The owner (KNambiarDJsc) demonstrates it to research teams and wants the interface
to be clear, calm, fast and **honest**. Work like a careful senior product engineer: read first, change little, look at
the result in a real browser, prove everything. You are not to start new product modules or change the engine, the
safety rules or the data model unless the owner asks.

## 1. Read, in this order, then do not re-explore the repository

1. `AGENTS.md` (rules for every agent here; they override your defaults).
2. `DESIGN.md` (the interface contract: honesty rules, colour tokens, typography, motion tiers, states, writing,
   accessibility gate, anti-patterns, sections 6c and 6d for the Studio, the journey and the Agent page).
3. `docs/demo/READINESS_REPORT.md` and `docs/demo/RUNBOOK.md` (what is verified, what the demo does).
4. `docs/EXECUTION_AND_FLOW.md` (every page and every flow, who may do what, what is real versus simulated).
5. `docs/handoff/SESSION_HANDOFF.md` and `harness/progress.md` (newest entries), `harness/decisions.md` (D-026, D-037 to
   D-042), `harness/blockers.md`.

## 2. What the product is

One platform for robotics and laboratory teams, built on the **OpenMHS** verification engine (a pinned Rust binary,
`engine.lock.json`, never modified; the platform computes no statistic). A researcher configures a simulated procedure,
a **second person approves** what runs, a durable worker executes it on simulated instruments, OpenMHS judges the
instrument's own report against an independent measurement, and everything is kept with digests. Stack: Next.js 15 web
app (`apps/web`), FastAPI + PostgreSQL + a durable worker (`services/api`), the Strands agent harness
(`packages/agent-harness`, its own uv project), a LabThings virtual laboratory and simulation hosts (`runtimes/*`).

Pages (sidebar): Get started, **Lab experiment** (a guided six-step journey), **Agent**, Workbench, Experiments (the
Studio), Digital twin, Hardware Hub, Workflows; Overview, Releases, Verification, Incidents, Evidence; Fleet;
Integrations, Settings. OpenMHS verdicts appear as SATISFIED/VIOLATED, "Supported success", "Contradiction", intervals and
"insufficient evidence".

## 3. What has been done (so you do not redo or undo it)

- **State:** `main` is at `6a297c8` or later. `origin/main` is behind: the last pushed commit is `82645f4`. Local,
  unpushed commits since: the code-map refresh and later work, the execution document, the harness changes, the Agent page
  and journey, the demo kit, and the Haiku model change. All 56 features in `harness/features.json` are verified.
- **Design pass:** motion tokens and overlays (`--dur-fast` 80 ms, `--dur-moderate` 160 ms, `--dur-slow` 240 ms,
  `hover` and `selected` overlay tokens), route-content fade, palette entrance, badge colour fade, press as an inset
  shadow, reduced motion keeps colour fades and drops movement (DESIGN.md section 10). Visual review of the older pages
  at 1280x800 in both themes: tables no longer hide their last column (headers wrap, soft scroll edge), the Workbench run
  list shows the name above the time, incident verdicts are badges, the organization form lost a stray divider.
- **Agent page** (`/agent`, `apps/web/src/components/Agent.tsx`, backend `services/api/app/agent/sessions.py`, D-040):
  runs the harness as the signed-in user, read-only, caps per session and day, engineers only, answer plus cost plus
  collapsed trace, an optional **draft** follow-up that a person files with one click, a plain-words state for a provider
  outage, a working indicator (elapsed seconds, "you can leave this page").
- **Lab experiment journey** (`/journey`, `Journey.tsx`): discover, configure (tolerance shown in words), request and
  approve (a different person), inspect the successful and failing runs, investigate, export. Status of each step comes
  from stored data.
- **Platform changes behind it:** `dispense-with-fault` workflow template (a journaled step injects a simulated fault and
  another clears it), a proposal cannot be approved by its proposer (403), run evidence reports (`report.html`,
  `report.json`, same bytes on repeat, Workbench "Evidence report" and "Download JSON"), a 3D scene that no longer reports
  ready after a failed mesh download.
- **Harness:** fixed questions and a rule-based investigation work without a model (labelled "no model"), drafts are
  recorded in the trace and sent nowhere, a note marked as the platform's own is added when evidence is simulated or when
  an answer claims a draft that was never recorded, transient provider errors are retried twice.
- **Demo model:** `anthropic/claude-haiku-4.5` through an OpenAI-compatible endpoint (`gpt-oss-120b` stopped supporting
  tool calls on the provider on the day).
- **Verification on the final tree:** `verify.sh` all gates passed (pytest 315 passed, 5 skipped; harness 28; web unit 57);
  `smoke.sh --e2e` 56 passed, 13 skipped with 2 workers; a rehearsal of the whole journey passed 24 of 24 steps.

## 4. The interface contract in one screen (read DESIGN.md for the rest)

- **Honesty first.** A number on screen comes from stored data or engine output; no decorative charts or sample values.
  Simulated evidence is labelled everywhere; unknown is its own colour and never success; a violated trial is not a
  release regression. Nothing is shown for a module that does not exist.
- **Colour:** tokens only (`bg`, `panel`, `sunken`, `line`, `ink`, `muted`, `faint`, `accent`, `ok`, `warn`, `bad`,
  `unknown`, `-soft`, `hover`, `selected`); one accent; semantic colours are states, not decoration. Never write a hex
  value in a component. All text tokens pass WCAG AA on their surfaces (`faint` on the `selected` overlay does NOT: use
  `muted` there).
- **Motion:** the fluid-functionalism approach, in the repository's own tokens: the bigger the thing that moves, the
  slower; animate `opacity` and `transform` only; exits quicker than entrances; reduced motion means fewer and gentler,
  not none. No animated charts, no skeleton shimmer, no looping animation.
- **States:** every data view has loading, empty (what is missing and the next action), error (what failed, in the
  user's terms, and how to retry) and success. Signed-out visitors see the sign-in prompt, never data.
- **Writing:** plain, specific, engineering register, sentence case, no marketing language, no exclamation marks;
  plain words before identifiers; timestamps through `<Time>`.
- **Accessibility gate:** `e2e/a11y.spec.ts` runs axe (WCAG 2.0, 2.1, 2.2 A and AA) on every page in both themes against
  real data. A new or changed page is added to its list in the same change. Visible text is part of every accessible
  name. Dialogs trap focus and return it.
- **Anti-patterns (reject):** gradients, glass, glowing borders, nested rounded cards, hero headings inside the app,
  decorative charts, generic robot illustrations, chatbot takeover, more than one accent, navigation for unbuilt modules.

## 5. Known UI and UX gaps: your backlog, in suggested order

Fix each at its cause, show it in a real browser (screenshots in both themes at 1280x800, then 768 and 390 widths), and
keep the change small.

1. **Agent answers show raw Markdown** (`**Short answer**`, bullet dashes). Render a safe subset (bold, lists, inline code,
   paragraphs) without `dangerouslySetInnerHTML`; keep the cited ids readable.
2. **Cited ids are not links.** `run:<id>`, `verification:<id>`, `contract:<digest>` in an answer or trace should open the
   Workbench run or the relevant record where one exists.
3. **Own-proposal approval is a dead end.** On Workflows an engineer sees an enabled Approve on their own proposal and gets
   a 403 message after the click. Disable it with the reason ("someone else must approve") and keep the server rule.
4. **Overview and Releases are near-duplicates** (both list the same projects). Ask the owner before merging or
   removing one; do not decide alone.
5. **Evidence "Kind" column** shows identifiers first (`engine_store (engine output)`); put the plain meaning first.
6. **Lab experiment page:** review the six steps on narrow screens; make step 3 clearer about who can do what for the
   signed-in role; check that "Done" never overstates (it must follow stored data only).
7. **Agent page:** the session list and trace are dense; consider relative times beside the exact timestamp, clearer
   refused or failed steps in the trace, and a visible difference between "no answer" and "stopped by a limit".
8. **Command palette exit animation** is not built (DESIGN.md says so): add a deferred unmount that keeps focus return
   correct, or leave it and say so.
9. **Pages never reviewed visually at all in this pass:** Digital twin, Experiments (reviewed in an earlier session),
   Settings, Integrations on mobile. Mobile and tablet widths have **not** been reviewed anywhere.
10. **Browsers:** only Chromium is tested. Do not claim others.

## 6. Hard rules

- **Commands go only to simulated environments** (D-026). Never send a command to hardware. Do not change the approval
  rules (D-037, D-041): a requester never approves their own request.
- **Verdicts and statistics are the engine's.** Never compute a statistic in the UI. Never fabricate telemetry,
  measurements or test outcomes.
- **Never weaken, skip or delete a test** to make a gate pass. If the same failure happens twice, stop and diagnose.
- **Git:** commits are local, in the owner's voice, with NO AI attribution, no `Co-Authored-By`, no "Generated with"
  line. Use `git commit -F <file>`. **Never push without the owner's explicit approval for that push.** Another agent may
  also commit here: read `git status` and `git log` first, never revert what you did not write, keep commits small.
- **Secrets and spend:** never write an API key into a file, log, commit or prompt. The model key lives only in the
  environment of the process that starts the stack (`PAP_LLM_*`). UI work needs no model: do not run live-model sessions
  without the owner's explicit approval, and cap any spend. The key was pasted into a chat earlier and must be rotated by the
  owner; never ask for it again.
- **Do not modify upstream repositories** (OpenMHS, OpenAMRobot). Do not start Docker locally.
- **No new dependency** without a row in `docs/open-source-integration-registry.md` first (animations use CSS tokens, not
  a library).

## 7. How to run, look and test

```bash
git add -N . && NODE_OPTIONS=--max-old-space-size=2048 bash scripts/verify.sh        # the full gate (about 10 min), ONE command, log to a file
PAP_E2E_WORKERS=2 NODE_OPTIONS=--max-old-space-size=2048 bash scripts/smoke.sh --e2e  # builds the web app, starts a stack, runs the browser suite
bash scripts/demo_up.sh && uv run python scripts/journey_seed.py --org lab-journey      # a stack to look at; stop with: touch var/demo/stop
npm --prefix apps/web run build        # needs NODE_OPTIONS=--max-old-space-size=2048
cd apps/web && npx tsc --noEmit && npx eslint src e2e
```

- Playwright is installed in `apps/web`; take screenshots with a small Node script run with
  `NODE_PATH=apps/web/node_modules` (sign in at `/settings` with the `Subject` field, theme through the `pap_theme`
  cookie, `reducedMotion: "reduce"` for stable captures). LOOK at the images: tests do not judge layout.
- Browser projects run in order: `chromium` (everything else), then `worker-recovery`, then `lab-journey` (they use the one
  shared virtual laboratory and worker). To run one spec against a running stack:
  `PAP_WEB_URL=http://127.0.0.1:3000 npm --prefix apps/web run e2e -- e2e/journey.spec.ts --project lab-journey --no-deps`.
- A changed page needs: types and lint clean, its a11y entry, the affected specs, then the full gate once per milestone.
- The API schema and the web client types are generated: after an API change run `uv run python scripts/export_openapi.py`
  and `npm --prefix apps/web run gen:api`.

## 8. Pitfalls on this machine (learned the hard way)

- **RAM is scarce** (often 1 to 3 GB free of 16): do not run a build and a browser suite at once; close programs; the
  browser suite is **load-sensitive** (five full runs on near-identical builds: three green, two with 1 to 3 timeouts in
  unrelated tests while API calls took up to 17 s; each failing test passed on a rerun). Use `PAP_E2E_WORKERS=2`. Diagnose
  before retrying; the earlier flakes were real defects (a 3D mesh failure reported as ready; a spec competing with a
  worker-killing spec), found from traces, not from guessing.
- **Leaked processes:** the demo stop file does not stop the Gazebo host (port 8867); a later stack then fails with "port
  in use". List processes by command line (`physical-ai-platform`, `pap_`) and stop only those.
- **Shell transport:** long heredocs and backslash escapes can be mangled. Write files with the file tools or a small
  script file; build special characters from code points.
- **Fix-forward on gates:** the secret scan flags fake keys that look like `sk-`; lint wants lines of at most 120
  characters; mypy flags unused `type: ignore`.
- **Provider dependence:** the agent needs a provider that supports tool calling; on the demo day one was down for it. The
  page says so plainly and the rule-based investigation still works.

## 9. How to work and how to report

For each backlog item: write down the acceptance criterion (what a user will see), implement the smallest change, look at
it in both themes and at 1280, 768 and 390 widths, run the affected specs, update `DESIGN.md` if the contract changed,
update `harness/progress.md`, commit locally. Stop and report after each group of three items.

Final report, short: what you changed and why (with screenshots paths), what you verified (commands and counts), what you
skipped and why, what still reads poorly, and what only the owner can do (decide Overview versus Releases, rotate the key,
approve a push). Say plainly what is not verified.

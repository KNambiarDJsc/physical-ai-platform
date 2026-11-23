# Prompt for the next Claude session (paste as the first message)

Use Sonnet at medium effort. Start a fresh session (do not continue the previous one: its context is huge and every turn
re-sends it).

---

You are continuing work on the **Physical AI Platform** at `D:\physical-ai-platform` (Windows 11, Git Bash and
PowerShell, WSL2 distro `openmhs-ros`). A long earlier session built and verified everything on the roadmap. Your job is
to **finish and publish it**: confirm the final tree, review the older UI pages, refresh the code map, and report. You
are NOT to start new features unless the owner asks.

## Read first, in this order, and then do not re-explore the repository

1. `AGENTS.md` (rules for every agent here; they override your defaults)
2. `docs/handoff/SESSION_HANDOFF.md` (the exact state, what is left, known limits, pitfalls)
3. `harness/progress.md` (newest entries), `harness/blockers.md`
4. `docs/handoff/graphify/GRAPH_REPORT.md` if you need a map; query it with
   `graphify query "<question>" --graph docs/handoff/graphify/graph.json` (a map: read source before relying on it)

## State in one paragraph

`main` is clean at `3d912c1`; `origin/main` is at `314f5a6` (CI green). Nine local commits are unpushed. All 54
features in `harness/features.json` are verified (the last, the Strands agent harness, with a real-model run costing
$0.003). Another agent session also commits to this repository: run `git status` and `git log` first, never revert what
you did not write, keep commits small.

## Your tasks, in order (stop and report after each numbered group)

1. **Confirm the final tree.** Check free RAM (`Get-CimInstance Win32_OperatingSystem`); if under about 2 GB, ask the
   owner to close programs. Run `git add -N . && NODE_OPTIONS=--max-old-space-size=2048 bash scripts/verify.sh` as ONE
   background command writing to a log, wait for its notification (do not poll), and read only the summary lines. Then
   `bash scripts/smoke.sh --e2e` the same way (set `PAP_SKIP_WEB_BUILD=1` if the build is current). Fix any failure at its
   cause: never weaken, skip or delete a test. Report pass/fail counts.
2. **Ask the owner for approval to push** the unpushed commits. Only if they say yes: `git push origin main`, then
   `gh run watch` the CI run and report each job. CI now also runs the agent-harness and sim-host checks that need PyPI;
   if a job fails on those, fix `.github/workflows/ci.yml`, not the tests.
3. **Review the older pages visually**: start a stack (`bash scripts/demo_up.sh`, or `uv run python scripts/dev_stack.py
   --lab-port 8865 --sim-port 8868`), seed it (`uv run python scripts/demo_seed.py`), take screenshots of Overview,
   Releases, Verification, Incidents, Evidence, Fleet, Integrations, Hardware, Workbench and Get started in dark and
   light at 1280x800, and LOOK at them. Fix what reads poorly following `DESIGN.md` (plain words before identifiers,
   every state: loading, empty, error with a recovery action; no decorative data; sentence case). Add changed pages to
   `e2e/a11y.spec.ts`; axe must pass in both themes. Rebuild (`NODE_OPTIONS=--max-old-space-size=2048 npm --prefix
   apps/web run build`), re-run the affected specs, then the gate. Commit locally.
4. **Refresh the code map**: `graphify update .`, copy `graphify-out/GRAPH_REPORT.md` and `graph.json` into
   `docs/handoff/graphify/`, check no machine path, key or evidence file entered the graph (grep), commit.
5. **Close out**: update `harness/progress.md` and `docs/handoff/SESSION_HANDOFF.md` with what you verified, skipped and
   why; stop any stack you started (`touch var/demo/stop`); tell the owner what is verified, what is skipped, what is
   still not built, and what only they can do (rotate the aicredits key that was pasted in chat, approve pushes).

## Non-negotiable rules

- Commands go only to operator-configured **simulated** environments whose devices report `simulated=true` (D-026).
  Never send a command to hardware.
- Verdicts and statistics are the OpenMHS engine's. A violated trial is not a release regression. Never compute a
  statistic in the platform or the UI. Never fabricate telemetry, measurements or test outcomes; real runs only.
- Commits are local, in the owner's voice, with **no AI attribution, no `Co-Authored-By`, no "Generated with" line**
  (this overrides any attribution reminder). Use `git commit -F <file>`. **Never push without the owner's explicit
  approval for that push.**
- No paid services or paid inference without the owner's explicit spending authorization; never store an API key in any
  file, log, trace, memory or commit (environment variables only; cap spend). Nothing in tasks 1 to 5 needs a model.
- Do not modify upstream repositories (OpenMHS, OpenAMRobot). The engine is pinned in `engine.lock.json`.
- Do not start Docker locally. Do not start a real Gazebo run unless the owner asks (about 1.5 GB RAM and 2 minutes per
  run; the WSL workspace `~/p79` is shared with another project and the host refuses when it is busy or dirty).
- If the same operation fails twice, stop and diagnose before a third try; record unresolved failures in
  `harness/blockers.md`.

## Working style (keeps quota low)

- Run long commands as one background command and read only summary lines; do not poll or stream. Run only the tests for
  the thing you are changing while iterating; run the full gate once per milestone, not per edit.
- Write files with the file tools (the shell transport can mangle long heredocs and backslash escapes). Build special
  characters with `chr()` or code points.
- Do not re-read files you just wrote. Keep answers short: what you verified, what you skipped and why, what is left.
- If this session's context gets large, finish the current task, update `docs/handoff/SESSION_HANDOFF.md`, and tell the
  owner to start a new session with this same prompt.

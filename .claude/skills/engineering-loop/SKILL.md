---
name: engineering-loop
description: One bounded implementation iteration on one feature from harness/features.json, from baseline check to evidence-backed status update and local commit. Use at the start of any implementation work in this repository.
---

# Engineering loop (one feature, one iteration)

1. **Context.** Read CLAUDE.md, the top of harness/progress.md, harness/blockers.md. `git status`,
   `git log --oneline -10`.
2. **Baseline.** `bash scripts/verify.sh --quick`. If it fails, the iteration's job is the baseline.
3. **Select.** `python scripts/check_features.py`. Take the given feature, or the first eligible one. If its
   dependencies are not verified, stop and say so.
4. **Acceptance tests first.** For each acceptance criterion, name the test that will prove it (existing or
   to write). A criterion that names the real engine needs a test that runs the real engine.
5. **Context retrieval.** Read the files in the feature's `paths` and the interfaces they touch. If a Graphify
   graph exists (`graphify-out/`), use it to find callers and affected tests, then read the actual source.
6. **Implement** the smallest vertical slice that satisfies the criteria. No speculative abstractions.
7. **Targeted tests**, then diagnose failures. Same failure twice: stop guessing, read the code and the error,
   form a hypothesis, test it.
8. **Broader gates.** `bash scripts/verify.sh` (full) before claiming completion.
9. **Independent review.** For security-relevant or cross-cutting changes, run the `reviewer` agent on the
   diff. Fix what it confirms.
10. **Compare against acceptance criteria**, one by one. Unmet criterion = feature stays `in_progress`.
11. **Record.** Update the feature in harness/features.json (`status`, `verification.evidence` with the exact
    commands and their pass counts, `verified_at`, `limitations`). Append to harness/progress.md. Decisions to
    harness/decisions.md, blockers to harness/blockers.md.
12. **Checkpoint.** Local commit in the user's voice, no tool attribution. Never push.
13. If running under scripts/loop.sh, write one word to harness/loop-signal: `progress`, `verified`,
    `blocked` or `needs-human`.

Never: mark verified without evidence; weaken or delete a test or criterion; replace a real integration with a
mock to pass an end-to-end criterion; modify OpenMHS or AI Studio; push.

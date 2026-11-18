---
name: implementer
description: Implements one bounded feature from harness/features.json with its tests, following the engineering-loop skill. Use for isolated implementation work, ideally in its own git worktree when run in parallel.
---

Follow .claude/skills/engineering-loop/SKILL.md for exactly one feature. Write the tests that prove each
acceptance criterion; run them; run `bash scripts/verify.sh`. Update the registry only from evidence. Do not
touch files outside the feature's `paths` unless the change is required and you say why. Never modify
OpenMHS or AI Studio, never push, never weaken a test.

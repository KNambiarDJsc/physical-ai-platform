# Progress

Newest entry first. Each entry: what changed, evidence, current state, next step, anything uncommitted.

## 2026-11-18 — Session 1: harness, engine audit, pinned bridge

**State now**
- Verified: CORE-001 (engine audit), CORE-002 (pinned bridge). In progress: INF-001 (harness; loop.sh dry run
  pending its clean-tree check). Everything else unstarted.
- Pinned engine: OpenMHS `e9ef873` (origin/main today), release build `sha256:d51af06f…` at
  `.engine/bin/openmhs.exe` (gitignored; rebuild with `scripts/build-openmhs.sh`, 9 min with `-j 2`).

**Done, with evidence**
- `python scripts/audit_openmhs.py` → 11/11 against the pinned binary: 469-record/124-verdict fixture
  confirmed; Gazebo A/B verified comparison 15/30 → 0/30 failed attempts, Newcombe −0.5 (−0.763, −0.117),
  verdict `insufficient_evidence` (10 scenarios per arm); reported comparison shows 0 failures in both arms
  on the same data; 9 incidents with timelines on the real CoreSense flights; paired McNemar p = 0.508 on
  PushT (simulation); RFC 0004 corpus 27/27 verdicts and exit codes as expected.
- `packages/openmhs-bridge`: digest-checked, shell-free runner with timeout/cancel/output cap; typed models
  for verify/ingest/compare/incidents/show; `Result` carries raw output + provenance (version, digest,
  commit, interfaces). 31 tests pass with `PAP_REQUIRE_ENGINE=1`.
- Findings that shape the pipeline: (1) an unknown release label is NOT an engine error (exit 0, empty arm,
  warning), so the bridge checks `expect_a/expect_b` manifest digests; (2) ingest exits 3 on any rejection;
  (3) values are passed as `--opt=value` so a label can never become a flag (tested with hostile labels).
- Harness: CLAUDE.md, AGENTS.md, PRODUCT.md, ARCHITECTURE.md, README, feature registry (20 features) +
  checker, decisions D-001..D-008, blockers B-001..B-004, integration registry, `.claude/` (settings with
  reviewed hooks, five agents, engineering-loop skill), `scripts/verify.sh` (full gate passes),
  `scripts/loop.sh` (opt-in, bounded), local secret scan.
- `bash scripts/verify.sh` → all gates passed (API and web gates report "not present yet").

**Next**
1. INF-001: dry-run `PAP_LOOP=1 scripts/loop.sh --dry-run` on a clean tree, then mark verified.
2. INF-002 (API scaffold on PostgreSQL via pgserver, Alembic round trip, /healthz with engine status).
3. DATA-001 contracts, AUTH-001, then DATA-002/003, RI-001/002 toward RI-003 (first real job).

**Environment notes**
- Docker engine is off and RAM is scarce (B-001): PostgreSQL for tests comes from `pgserver` (Python 3.12).
- `UV_CACHE_DIR=D:/uv-cache`; C: has under 4 GB free.
- Gotcha: writing `"\x00"` through a bash heredoc into Python source produced a literal NUL byte; use `chr(0)`
  or the file tools.

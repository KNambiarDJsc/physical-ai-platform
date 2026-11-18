# OpenMHS capability audit (CORE-001)

Pinned commit `e9ef873b42f74f201aecf392ee6e61453e1f40a4` (OpenMHS `main`, 2026-11-18). Re-run with:

```
OPENMHS_BIN=<binary> python scripts/audit_openmhs.py      # writes harness/evaluation-results/openmhs-audit.json
```

Status meanings: **verified by run** = this repo's audit script executed it and checked the result;
**present in source** = code and upstream tests exist, not exercised here; **not used** = outside the
platform's needs for now.

| Capability claimed | Status | Evidence | Platform use |
|---|---|---|---|
| Outcome verification, SATISFIED / VIOLATED / UNKNOWN (RFC 0004) | verified by run | 27/27 corpus cases (6 satisfied, 6 violated, 15 unknown) match expected verdicts and exit codes 0/3/4 | Per-episode verdicts |
| Verifier report with reasons, per-condition observed values, accepted/rejected records | verified by run | `placed` case report; reasons such as `evidence.missing`, `calibration.expired` in corpus | Episode drill-down |
| Event ingestion, RFC 0005 envelope, idempotent by `event_id` | verified by run | gazebo_ab: 1117 accepted, 4 duplicate, 0 rejected; coresense: 467 accepted, 2 duplicate | Engine store per job |
| Fixture with 469 records and 124 outcome verdicts | verified by run | `coresense_real_flights_verified.jsonl`: 469 records, 124 `outcome.verified` | Bridge regression test |
| Release comparison | verified by run | `ops compare --verified` engine-bullet → tol-0.01: attempts 15/30 → 0/30 failed | Release Intelligence |
| Wilson intervals | verified by run | arm a ci95 [0.2366, 0.7634] for 5/10 scenarios | Shown as is |
| Newcombe difference interval | verified by run | −0.5 (−0.763, −0.117), `difference_method: newcombe` | Shown as is |
| Scenario counting (replicates not treated as independent) | verified by run | `unit: scenario`, warning "attempts repeat scenarios" | Shown as is |
| `insufficient_evidence` verdict with reasons | verified by run | "fewer than 30 scenarios with a known outcome in an arm (a 10, b 10)" | Shown prominently |
| Paired comparison (McNemar exact, paired Newcombe) | verified by run | PushT (simulation) 20 pairs, p = 0.508, +15 pts (−13.4, +40.4) | Optional per job |
| Stratified comparison by site | present in source; output seen | `strata[]` per site in compare output; Mantel-Haenszel risk difference in `stats.rs` | Shown per site |
| Reported vs verified kept separate | verified by run | same store: reported 0/30 failures both arms, verified 15/30 vs 0/30 | Core of the product |
| Incident reconstruction (`ops incidents`, `ops show` timeline, failure shape) | verified by run | 9 incidents on real flights; `show` returns 42 members and a shape | Linked from comparisons |
| Deployment manifests, rollouts, "what changed" | present in source; manifests verified by run | manifests resolved by release label in compare | Releases = manifests |
| SQLite local evidence store | verified by run | per-run `ops.sqlite` | One store per job |
| ROS 2 / rosbag2 ingestion | present in source (Python importers) | `coresense_aerostack2.py` reads rosbag2 SQLite with a stdlib CDR decoder | Not called by the platform; teams run it locally and upload events (OpenMHS-native input) |
| MCAP / Gazebo | present in source (Python importer) | `openamr_gazebo.py` turns recorded Gazebo runs into events | Same as above |
| LeRobot | present in source (Python importer) | `policy_rollouts.py` for LeRobot rollout outputs | Same as above |
| Rust execution gateway, MCP server | present in source | crates `openmhs-gateway`, `openmhs-mcp` (rmcp ~3.10) | **Not used**: the platform is observation-only |

## What the platform depends on

Only the CLI subcommands `outcome verify`, `ops ingest`, `ops compare`, `ops incidents`, `ops show`, each
with `--json`, and the record formats `openmhs.event/0.1`, `openmhs.deployment/0.1`,
`openmhs.artifact/0.1` and RFC 0004 contract/evidence v0.1. Nothing else.

## Not re-run here

The upstream Rust test suite (about 709 tests at `41b6ce8` per the OpenMHS project notes) was not re-run
in this audit; building and testing the full workspace needs more RAM and disk than the workstation has
free. The release build of `openmhs-cli` at the pinned commit is the binary under audit.

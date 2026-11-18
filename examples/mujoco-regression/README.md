# Controlled regression experiment: MuJoCo reaching arm (Milestone C)

A known regression injected into a simulated controller, evaluated through the platform (API, worker, pinned
OpenMHS engine e9ef873), with a no-change control. Design, sample size and predictions were committed **before**
the held-out run: [PREREGISTRATION.md](PREREGISTRATION.md) (commit 0971184). Evidence class: `simulated`.

## Result

150 episodes per group, 600 in total, all accepted by the mapping (0 rejected), every episode measured.

| Comparison | Robot-reported failure rate | Verified failure rate (fingertip > 2 cm at the report) | Engine verdict, reported / verified | Prediction |
|---|---|---|---|---|
| A (10 ms) vs B (50 ms) | 3.3 % -> 100 % | 0/150 -> 146/150 (97.3 %, 95 % CI 93.3-99.0); difference +97.3 pp [+92.6, +99.0] | regression / **regression** | held |
| A vs D (20 ms) | 3.3 % -> 100 % | 0/150 -> 32/150 (21.3 %, 95 % CI 15.5-28.6); difference +21.3 pp [+15.0, +28.6] | regression / **regression** | held |
| A vs C (no change) | 3.3 % vs 4.7 %; difference +1.3 pp [-3.5, +6.4] | 0/150 vs 0/150; difference 0 [-2.5, +2.5] | insufficient_evidence / **insufficient_evidence** | held: no false regression |

Paired by initial condition (A vs B, A vs D share seeds): 146 and 32 pairs where only the degraded controller
failed, 0 the other way (McNemar p 2e-44 and 5e-10, engine output). All figures are engine outputs in
`results/*/report.json`; the platform computed none of them.

## What the platform showed that a pass/fail rate alone would not

- **The robot's own reports overstated the 20 ms regression about 4.5-fold.** It reported a timeout in all 150
  D episodes (+96.7 pp), while the fingertip was within 2 cm in 118 of them (+21.3 pp verified). The latency makes
  the joints jitter, so the robot's "joints still" check never holds; the arm is mostly where it should be.
  These 118 episodes are **contradictions** (robot: timeout; evidence: reached), and each one can be opened in
  the episode view with the verifier's condition, the measured error and the robot's own estimate. Example:
  `D-1000`, robot reported timeout, measured fingertip error 17.0 mm (robot's own estimate 12.5 mm): reached.
- **The no-change control produced no regression verdict**, for either reported or verified outcomes.
- **All contradictions in A and C are the same kind** (5 and 7): the robot reported a timeout although the
  fingertip was within 2 cm, because its stillness check did not settle within 3 s.

## Where the result needs care

- **The 20 ms "regression" is a shift in accuracy, not a cliff.** Median fingertip error at the report: A 4.3 mm
  (max 7.6), D 15.7 mm (max 23.7), B 102 mm. All 32 D failures are marginal misses (20.0-23.7 mm, median 20.9).
  The binary 2 cm contract turns a 3.6-fold loss of accuracy into "21 % failures" and hides how close the rest
  of D is to the line. The engine compares failure *rates* only; it has no comparison of the measured distances
  themselves. Recorded as engine gap G-7 in `docs/engine-contract-gaps.md`; not substituted in Python.
- **The no-change control can only ever say "insufficient evidence" here.** With a near-perfect baseline (0
  verified failures in 150) the engine declines to judge ("fewer than 5 failures in both arms"), and even with
  failures its interval [-2.5, +2.5] pp is wider than its +-1 pp no-change margin. "No false regression" is
  demonstrated; "no change established" is not, and would need far more episodes or a different margin.
- **One prediction's mechanism was wrong.** The pre-registration expected A's and C's few contradictions to come
  from the calibration error near the 2 cm boundary. None did: the robot never claimed success outside 2 cm; all
  contradictions are timeouts with the fingertip inside. The count held, the reason did not.
- **D was chosen on the pilot**, not before it (B was declared beforehand). This is stated in the
  pre-registration; the held-out seeds were never used to choose anything.

## Limitations and possible confounders

- Simulation only: an idealised arm, contact-free task, no sensor noise beyond encoder quantization, latency
  applied in whole 10 ms control periods (so 20 ms is the only step between 10 and 30 ms).
- The robot's "self-report" is a rule written for this experiment, not a production controller's; its stillness
  threshold was corrected on the pilot (0.05 -> 0.2 rad/s, below one encoder count per period before).
- The calibration error (3 mm per link) is the same in every group, so it cannot explain differences between
  groups, but it does shift every measured error slightly.
- Episodes are simulated on one clock with start times 10 s apart; times carry no physical meaning.
- One task, one controller family, one degradation type.

## Resources (measured)

CPU only, headless, one process. Peak resident memory 57.8-61.6 MB per group (budget 400 MB, checked after every
episode). Simulation wall time 0.9-2.0 s per 150 episodes (Windows, Python 3.12.11, MuJoCo 3.17.0, numpy 2.5.4).

## Product evaluation (Step 6), measured on this machine

| | Measured |
|---|---|
| Import evidence (4 releases, 4 CSV uploads, 1 mapping) through the API | 0.21 s |
| Manual mapping effort | one 40-line `mapping.json`, written once; no code |
| Time to a verdict (300 episodes, 300 verifier runs, 3 engine comparisons) | 10.2-12.3 s per comparison |
| Explaining one failure | episode view: robot report, verifier condition, measured value, source row |
| Report reproducibility | rollouts regenerate byte-identically from code + seeds (test); a report is byte-identical on every download; a second evaluation gives identical statistics |
| No-change control | no unsupported regression verdict; but also never "no change" (see above) |

Against a standalone analysis script (not measured here, an estimate): a 20-line pandas script would compute the
two failure rates in under a second and is easier to adapt, e.g. to compare the median error, which the platform
cannot do today (G-7). What the script would not give without further work: the reported/verified split and
per-episode contradictions, paired intervals with the engine's rules, provenance (engine build, mapping and
configuration hashes, input checksums) in every result, and a report that regenerates identically. Whether that
is worth the platform's overhead is not shown by this experiment: it passed because the injected effects are
clear. A fair comparison needs an engineer doing the same analysis both ways (Milestone D).

## Reproduce

```bash
uv run python examples/mujoco-regression/sim.py run --n 150          # data/*.csv + manifest.json (digests match)
uv run python scripts/dev_stack.py --api-port 8765 &
uv run python examples/mujoco-regression/evaluate.py --api http://127.0.0.1:8765
uv run pytest services/api/tests/test_mujoco_regression.py           # regeneration + the three comparisons
```

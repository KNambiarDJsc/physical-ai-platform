# Dry run (ours, not an external user's)

This is **us following our own instructions with a script**. No external engineer has done the exercise. The UI
part was driven by a browser-automation script (`apps/web/e2e/trial-exercise.spec.ts`), so its durations are
*lower bounds* on what a person needs, and it cannot tell us what is confusing. Do not read it as user feedback.

## What was checked

`trial/dry_run.sh` installs with `bash trial/start.sh`, does Part A through the web UI exactly as `EXERCISE.md`
says, compares every answer with `trial/expected.json`, runs the Part B commands, then runs `start.sh reset`.

| Check | Result |
|---|---|
| T1 organization and project created in the UI | done |
| T2 MuJoCo A vs D: both verdicts "Regression"; 32 verified failures and 118 contradictions in the candidate | matches the key |
| T3 one verified failure opened: the page's explanation text, the failed condition "fingertip within 0.02 m of the target" and a measured error above 0.02 m | matches the key |
| T4 A vs C: both verdicts "Insufficient evidence" with the reason "fewer than 5 failures in both arms together" | matches the key |
| T5 CoreSense: both "Insufficient evidence", the label "PHYSICAL EVIDENCE", 31 contradictions in the baseline | matches the key |
| T6 two JSON downloads have identical SHA-256 | identical |
| Part B, three commands: the script's verdicts, counts and intervals equal the engine's | `test_trial_baseline.py`, 14 cases |

## Run 1: local Windows stack (not Compose), 2026-11-19

Whole exercise through the UI in 40 s of automation (T1 1 s, T2 18 s, T3 under 1 s, T4 13 s, T5 7 s, T6 1 s).
This used the local development stack, **not** the Docker installation. It verifies the instructions and the
answer key, not `start.sh`.

## Run 2: clean GitHub runner, Docker, `bash trial/start.sh`

CI run [44458202782](https://github.com/KNambiarDJsc/physical-ai-platform/actions/runs/44458202782), commit
36d60e7, job `trial`, fresh `ubuntu-24.04` machine, no secrets in the job. Record in `dry-run-record/`.

| | Result |
|---|---|
| `bash trial/start.sh` from a clean checkout to "Ready" | **512 s** (engine compiled inside the image build, images pulled) |
| Exercise T1-T6 through the UI, every answer compared with `expected.json` | all matched; 12.5 s of automation |
| Part B, three script runs | 0.03 s each |
| `bash trial/start.sh reset` | removed the containers, the database volume and the network |

No steps were done by hand between those lines: the job is `bash trial/dry_run.sh` and nothing else. The only
extra tooling is the browser driver (Node and Playwright), which stands in for the engineer's mouse. The first
attempt at this run **failed**: `start.sh` generated its database password with `tr ... | head -c 32`, which dies
of SIGPIPE under `set -o pipefail`, so the script stopped before starting Docker. Nobody had run `start.sh` before
(Docker is off on the development machine), so only the clean run could find it. Fixed in 36d60e7.

## Where the plain script is faster or simpler

Measured on the same machine as Run 1:

| | Platform | Script |
|---|---|---|
| Setup | `start.sh`, 512 s on a clean GitHub runner (engine compiled in the image) | none (Python 3.10+, standard library) |
| Time to the T2 answer | 18 s of automation: create releases, upload three files, paste the mapping, fill the evaluation form, wait for the engine | 0.07 s |
| Time to the T4 answer | 13 s | 0.08 s |
| Time to the T5 answer | 7 s | 0.08 s |
| Edit the rule (say, 3 cm instead of 2 cm) | edit the mapping JSON, add a new mapping version, re-run the evaluation | change one number |
| Find one failing episode in `D.csv` (S4) | click through the episode view | one line of code or a spreadsheet filter |

The script also prints the number of episodes where the report and the measurement disagree (118 of 150), so for
the headline numbers the platform adds no information. What the script does **not** give you: the per-episode
record of which rule was applied and what was measured, a stored and checksummed record of the engine build,
mapping and input files, a report that regenerates identically, and access control. Whether that is worth the
difference above is exactly what the form asks an engineer.

## Problems found while preparing

- The comparison page shows the evaluation as "succeeded" a moment before the results appear; a first version of
  the driver read the verdicts too early and got nothing. A person would just wait, but it is a rough edge.
- The exercise depends on exact release labels and on pasting the whole mapping file; a typo costs minutes. That
  is real manual work and is recorded in the form (section 3).
- The first local attempt was killed when the machine ran out of memory (0.3 GB free) and left a damaged throwaway
  database. A later run worked with about 1.4 GB free. We have not measured the Docker stack's memory use, so
  `README.md` makes no memory claim; a small laptop may struggle.

## Not exercised

Human timing, confusion, and the form. Whether the instructions are clear to someone who has never seen the
repository. Windows and macOS Docker Desktop (the Windows run used the local stack, not Docker). A source-archive
install without GitHub access. Reaching the web page from a browser on a different machine.

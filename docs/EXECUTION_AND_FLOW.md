# How the platform executes things, and what the website does

A reference for an engineer or a research team seeing the platform for the first time: what runs, in what order, who is
allowed to start it, what each page shows, and what is real versus simulated. It describes what is built and verified
(54 of 54 features in `harness/features.json`); the last section lists what is not built. The 12-minute talk track is
`docs/DEMO.md`.

## 1. The idea in one paragraph

A change to a robot's software, or to a laboratory procedure, has to be proven, not assumed. The platform lets an
engineer run the change in **simulation**, requires a **second person to approve exactly what runs**, has a durable
worker execute it, and has an independent engine, **OpenMHS**, judge every result. Evidence and verdicts are kept with
digests, and recordings open in a 3D digital twin. The platform computes no statistic itself: every verdict is the
engine's, and when the evidence is too thin the answer is "insufficient evidence", not a guess.

## 2. Components

```
 Browser (Next.js web app)
        |  HTTPS, signed-in user (OIDC in production, development identity locally)
        v
 API service (FastAPI) ---- PostgreSQL / SQLite   metadata, jobs, audit
        |                \-- content-addressed storage (local or S3)   evidence, artifacts, recordings
        |
        +--> durable worker  (leases a job, journals each step, safety check, timeout, retry)
        |         |
        |         +--> adapter SDK (W3C WoT Thing Descriptions, LabThings)
        |                   |
        |                   +--> virtual laboratory      simulated pump + balance
        |                   +--> simulation hosts        Gazebo (real, in WSL) and a self-test host (kinematic model)
        |                   +--> ROS 2 observer          read-only, serves a recorded graph
        |
        +--> OpenMHS engine (pinned build, engine.lock.json)   the only source of verdicts and statistics
        |
        +--> agent tools (typed, allow-listed, run AS the caller)  <-- in-app assistant, MCP server, Strands harness
```

## 3. The three execution flows

### 3.1 Release Intelligence: compare two releases from recorded evidence

1. **Register** a baseline and a candidate release in a project (Releases).
2. **Upload evidence** (CSV or recordings). Files are size-limited, parsed defensively, stored by SHA-256, write-once.
3. **Map** the columns to the engine's episode fields with a declarative, versioned mapping.
4. **Start an evaluation.** A durable job runs the pinned OpenMHS engine over the episodes.
5. **Read the result**: per-episode verdicts, the engine's comparison (with intervals), a reproducible HTML and JSON
   report, and the incidents it grouped. A violated trial is one contract violation, never a release regression by
   itself; only the engine's release comparison can say that, and it needs enough known outcomes (30 per arm by default).

### 3.2 Workflow: ordered device actions with an independent check

1. A **workflow** is an ordered list of device actions with a verification contract (example: tare the balance, dispense
   50 µL with the pump, weigh; the contract says the delivered mass must be within 2 % of the volume as water).
2. An engineer **runs** it from the Workbench. The worker takes a lease, then for each step: safety check, send, journal
   before and after, wait for completion. A repeated request id never repeats a command (idempotent re-send after a crash).
3. **Two sources of truth are kept apart.** "Reported by the instrument" is what the pump claimed. "Independently verified
   (OpenMHS engine)" is the balance reading judged against the contract. They can disagree, and that disagreement is shown.
4. The run view updates by itself while it executes, then shows verdict, contract, engine build, digests and a timeline.
5. A finished run has an **evidence report** (`report.html`, `report.json`): the procedure's digest, every executed step,
   the instrument's claim and the independent measurement, the engine's provenance and any follow-up proposals. It is
   built only from stored records and has no generation time, so the same run always gives the same bytes.
6. **A genuine failing case.** The built-in template `dispense-with-fault` adds two visible steps to the same procedure: it
   injects a simulated fault (a partial blockage, for example) through the laboratory's simulation controls and clears it
   at the end. The pump still reports 50 µL; the balance measures about 0.031 g; the engine says VIOLATED, a
   *contradiction*. Nothing is edited afterwards.

**Two people.** Any member can *request* a run (a proposal); an engineer other than the requester approves it, and only
then is a run queued. The agent can only *draft* a follow-up; a person files it, and a different person still approves.

### 3.3 Experiment on a simulation host: request, approve, run, capture, judge

1. **Configure** (Experiments, Studio): pick an environment and a scenario the host lists. Set the setups ("arms", for
   example `main` vs `fix`) as columns, the repetitions, the pass rule, what to keep and which robot model shows the
   recording. Saving creates an **immutable, content-addressed version**; a change is a new version.
2. **Request.** Anyone in the workspace can ask to run a version. State: awaiting approval.
3. **Approve.** An engineer **other than the requester** approves the **exact checksum** (D-037). Nothing else starts a run.
4. **Compile and queue.** Approval compiles the version into one workflow per arm and queues the repetitions.
5. **Execute.** The worker sends `run_scenario` to the simulation host. The host runs only operator-listed scenarios, with
   a fixed argument list (never a shell string built from user text), one at a time, and **refuses rather than degrades**
   (D-038) when memory is short or the checkout is dirty.
6. **Capture.** The worker fetches each listed artifact, checks it against the digest the host reported, and stores it.
   An MCAP file is registered as a recording linked to the run.
7. **Judge.** The engine verifies each trial against the contract. Setups can be judged as releases for a comparison.
8. **Inspect.** Per trial: measurements, verdict, artifacts, and "Investigate in Digital twin".

Verified example: the OpenAMRobot command-loss regression (platform-sw #79). Pre-fix wiring: the base kept moving about
1.003 m after its commands stopped (violated, limit 0.15 m). Fix: 0.080 m (satisfied). Real headless Gazebo, run through
the platform.

## 4. Who may do what

| Role | Can |
|---|---|
| Viewer | Read everything in their workspace, including agent sessions; ask for an experiment run; request (propose) a workflow run |
| Engineer | Configure experiments and workflows; run workflows; ask the agent; approve or reject someone else's request (never their own: 403) |
| Admin | Everything above, plus members, projects and organizations |
| Someone outside the workspace | Gets 404: tenant isolation |

Commands go **only** to environments the operator configured as `simulated` whose devices also report `simulated=true`
(D-026). Physical environments are discovered and read, never commanded. The platform is never in a robot's real-time or
safety path.

## 5. The website, page by page

**Lab automation**

| Page | What it is for | What you see |
|---|---|---|
| Get started | First run | Five steps (workspace, environment, discover devices, workflow, run and read the verified result), each marked done |
| Lab experiment | The guided journey | Six steps from discovery to exported evidence: discover the pump, balance and simulation controls; see two procedures with their explicit tolerance; request a run (a different person approves); inspect the successful and the failing run; investigate with the agent; export. Each step's status comes from stored data and links to the page where the work happens |
| Agent | Ask and investigate | Ask about runs and experiments; the answer cites ids, shows its cost and full trace; an optional drafted follow-up that a person files. Read-only (`docs/agent-harness.md`) |
| Workbench | Run and watch | Live instrument values, observed robots, run list, the run (reported vs verified), steps, timeline, and an evidence report (page or JSON) for each finished run |
| Experiments | The Studio | Configure setups, request, approve, run, per-trial results, setups side by side, release verdict |
| Digital twin | Inspect a recording | 3D robot model, MCAP playback, event timeline, "Compare with" a second recording as a ghost, the engineering assistant |
| Hardware Hub | What is connected | Environments (kind, adapter, endpoint, devices, last discovery), each device's properties, actions and live reads |
| Workflows | Define and review | Compose a workflow across discovered instruments; recent runs; proposals awaiting an engineer's decision |

**Release intelligence**

| Page | What you see |
|---|---|
| Overview | Projects you can access; create a project or an organization |
| Releases | Pick a project, register releases, compare them; per-episode evidence; reports |
| Verification | One row per evaluation: robot-reported verdict vs independently verified verdict, agreement, episodes, contradictions |
| Incidents | Failures the engine grouped (a timeout, or a measured violation), with the engine's own explanation |
| Evidence | Every stored file, its kind, size, SHA-256, where it was used, who stored it |

**Operations and workspace**

| Page | What you see |
|---|---|
| Fleet | Robots that appear in the evidence, with outcome counts per release (counts, not rates) |
| Integrations | Sign-in mode, the pinned engine build, machine credentials for CI and robots, and the API calls pipelines use |
| Settings | Identity and sign-in, and workspace members |

Across the app: dark and light themes, a command palette (Ctrl K), keyboard access, WCAG A and AA checked by axe on every
page in both themes, quiet motion that respects reduced-motion settings, and every number traceable to stored data.

## 6. Where an AI model is, and is not

- **Web assistant** (Digital twin, select an event, "Explain this event"): rule-based. It calls the platform's read-only
  tools as the signed-in user and cites the evidence ids it relied on, plus what is not known. **No language model.**
- **Strands agent harness** (`packages/agent-harness`): a command-line component, also reachable from the website's
  **Agent** page (read-only, drafts only; `docs/agent-harness.md`). It works only through the
  same typed, allow-listed tools, as the person who started it. It can read, and with an explicit flag it may *record* a
  request for a person to approve. It has no tool to approve, run, edit or command a device. Providers are configuration,
  spend is capped per session and per experiment, every session leaves a trace, and answers are checked against the ids
  the tools returned. It has been verified with one real model on a small data set: safe, grounded behaviour there, not
  general investigation quality.

## 7. Real, simulated, and recorded

| Item | Status |
|---|---|
| Gazebo runs of the #79 regression | Real headless simulation, run by the platform (WSL) |
| Self-test simulation host | A small kinematic model, **not** a simulator; it exercises the pipeline |
| Virtual laboratory (pump, balance) | Simulated devices, labelled SIMULATED everywhere |
| OpenAMRobot graph on the Hardware Hub | A **recorded** snapshot replayed unchanged, not live |
| OpenMHS verdicts and statistics | Real engine, pinned by commit and binary digest |
| Hardware | None connected; no physical validation |

## 8. Limits, stated plainly

- One run per arm gives individual contract verdicts only; the engine's release comparison says insufficient evidence until
  it has enough known outcomes.
- The pre-fix Gazebo arm is the fix commit with two wiring files restored from `origin/main`, recorded in the run identity.
- No customer data, no hardware validation, no safety or regulatory certification claim.

## 9. Not built yet

MuJoCo and Isaac simulation hosts (same contract, no platform change); cancelling a running scenario; streaming large
artifacts to clients; agent plans that resume after an approval;
branching workflows; a split 3D view for two recordings beyond the ghost. Overview and Releases currently list the same
projects.

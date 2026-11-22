# Simulation execution and Experiment Studio

How an engineer registers an existing simulation environment, configures an immutable experiment, approves it, has it
run, and inspects the result, for any simulator, starting with Gazebo. Everything here reuses what exists: OpenMHS
(verdicts), the adapter SDK and Thing Descriptions (the host contract), the durable worker and workflow executor
(execution, safety, journaling), the evidence engine, content-addressed storage, and the Digital Twin Workbench
(inspection). There is no new physics engine and no new execution engine.

## Layers

| Layer | Owner | Here |
|---|---|---|
| Robot model | the robot's team | upstream's URDF and meshes in the model registry (TWN-001) |
| Simulator | the simulator and the operator | Gazebo, run by the operator's own launch scripts |
| Simulation host | operator (small, generic) | `runtimes/sim-host`: serves the `pap.simulation-host/1` contract, runs only the scenarios the operator listed |
| Platform | this repository | experiment specs, approval, compilation to workflows, execution, capture, results, twin |

## The host contract (`pap.simulation-host/1`)

A host is a W3C WoT Thing named `simulation-host` (LabThings, like the virtual lab), so the Hardware Hub discovers it with
the adapter that already exists. Nothing in the platform knows which simulator is behind it.

- property `simulated` (always true): the executor's safety check requires it, exactly as for every other simulated device.
- property `simulator`: kind (`gazebo`, `mujoco`, `isaac`, `selftest`), name, version, what it is.
- property `scenarios`: the operator's catalog. Each scenario has an id, a version, a JSON Schema for its parameters, the
  measurements it outputs (name, unit), the artifacts it leaves (name, media type) and a maximum duration.
- property `runs`: recent runs and their state.
- action `run_scenario(scenario, parameters, request_id)`: validates the parameters against the scenario's schema, runs the
  operator's fixed command (an argument list, never a shell string, never built from user text), waits, and returns
  `{run_id, state, measurements, artifacts[{name, sha256, size_bytes, media_type}], identity, started_at, finished_at}`.
  A repeated `request_id` returns the stored result and runs nothing (the executor then treats the step as idempotent and
  may safely re-send it after a worker crash). One run executes at a time; others wait for the lock.
- HTTP `GET /runs/{run_id}/artifacts/{name}`: the bytes of a listed artifact only.

The host reports what the scenario's own script measured and what files it left. It never invents a measurement: a
scenario that leaves no result file is a failed run.

## Experiment specification (`pap.experiment-spec/1`), immutable

An experiment is a name; each version is an immutable, content-addressed specification:

- `environment`: a registered simulated environment (operator catalog, discovered through the Hardware Hub).
- `scenario`: id and version, pinned. The spec is refused if the host no longer lists that version.
- `arms`: labelled variants, each with scenario parameters (validated against the discovered schema). One arm is a plain
  run; two or more is a controlled comparison.
- `repetitions`: trials per arm.
- `contract`: conditions over the scenario's named measurements, with units. The verdict is the engine's
  (`openmhs outcome verify`), never the host's.
- `capture`: which artifacts to keep, and whether to register an MCAP artifact as a recording in a project, on a model
  version, so it opens in the Digital Twin.

A change is a new version. Approval is of a version, never of a name.

## Execution

1. A person with the viewer role or above (or an assistant using one) REQUESTS a run of a version: state `awaiting_approval`.
2. An engineer APPROVES or REJECTS. Nothing else can start a run.
3. Approval compiles the version into one workflow per arm (a `run_scenario` step, evidence from the step's measurements,
   the spec's conditions) through the existing workflow service, and queues `repetitions` runs per arm. The durable
   worker executes them: lease, journal, safety check (simulated environment AND `simulated=true` on the host), step
   timeout from the scenario, engine verification.
4. After a run succeeds the worker fetches the listed artifacts from the host, checks each against the digest the host
   reported, and stores them content-addressed. An MCAP artifact is registered as a recording linked to the run.
5. Results: per trial the measurements, the engine's verdict and contract, the artifacts with digests, and "Open in
   Digital twin". Per arm the raw values and verdict counts. No statistic is computed in the interface; a comparison
   verdict comes only from `ops compare` over evaluated episodes (a later step).

## What is refused

Physical environments (D-026), unlisted scenarios, parameters outside the schema, a scenario version the host no longer
lists, a measurement the scenario does not output, an artifact the scenario does not leave, a digest that does not match,
and any request by someone who is not in the workspace (404).

## First scenario: OpenAMRobot command-loss stop (#79 / PR #177)

Host backend: Gazebo in WSL, run by the repository's own scenario scripts (`examples/openamr-cmd-timeout/scenario`).
Parameter `wiring`: `main` (pre-fix wiring) or `fix` (committed fix). Measurements: `travel_after_kill_m`,
`driven_before_kill_m` from Gazebo's world pose. Artifacts: the MCAP bag, its summary, the run identity, the probe.
Contract: travel after kill at most 0.15 m, upstream's own limit. The pre-fix arm is expected to violate and the fix arm to
satisfy it; that expectation is the acceptance test and it is checked against the engine's verdicts, not asserted.

## Preparation for camera-configuration comparisons

A camera comparison is an experiment with two or more arms whose parameters name camera profiles, a scenario that outputs
visibility measurements and leaves recordings, and the same objects and conditions in every arm (fixed in the scenario,
shown in the spec). The infrastructure for it is the arms, the pinned scenario schema, per-arm results and captured
artifacts above; the camera scenario itself belongs to the simulation owners (OpenAMRobot #69, #97) and is not built here.

## The Studio in the interface

`/experiments` (nav: Lab automation). Engineers configure; everyone in the workspace can read and ask for a run. The
journey: pick an environment and scenario the host lists, set the setups as columns of a comparison table (fields come
from the scenario's JSON Schema and are checked in the browser and again by the API), say how often and what counts as a
pass, what to keep and which robot model shows the recording, then save an immutable version. Someone other than the
requester approves the exact checksum; trials run in the worker; results show each trial's measurement and the engine's
verdict, setups side by side, downloadable files, and "Investigate in Digital twin" for each recording. The twin shows the
trial's arm, seed, verdict and an "SIMULATED EVIDENCE" label, links back to all trials, and its assistant explains an event
from the run's own verification and contract.

## Architecture note

Execution reaches a simulation host through the adapter SDK from the durable worker, as it reaches the virtual lab. It does
not pass through a separate OpenMHS Gateway process; the verdict is the OpenMHS engine's. Hosts for Gazebo, MuJoCo and
Isaac Sim implement the same `pap.simulation-host/1` contract; the platform does not know which is behind it.

## Not built yet

MuJoCo and Isaac hosts (the contract is the same), the Gazebo catalog entry (SIM-006), an automatic evaluation of arms
through Release Intelligence (`ops compare`), cancellation of a running scenario, a progress stream from inside a running
scenario, a twin view that plays a baseline and a candidate side by side, serving artifacts by streaming (they are bounded
by the 96 MiB capture limit), and policies or datasets.

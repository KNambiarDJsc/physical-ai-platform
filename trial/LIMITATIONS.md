# Known limitations

Read this before judging the platform. Each item is something we found, not something we are guessing at.

## What the verdicts can and cannot tell you

- **G-7: only pass/fail rates are compared, never the measured values.** In the MuJoCo data a 20 ms latency raised
  the median fingertip error from 4.3 mm to 15.7 mm, a 3.6-fold loss of accuracy. The engine saw only that 32 of
  150 episodes crossed the 2 cm line, every one of them a marginal miss (20.0 to 23.7 mm). A regression in
  *margin* is invisible until it becomes failures. The platform shows each episode's measured value but does not
  compare the distributions.
- **G-8: "no change" cannot be established for a very reliable baseline.** With 0 failures in both arms the engine
  answers "insufficient evidence" (fewer than 5 failures in both arms together), and even with failures its
  interval is wider than its 1-percentage-point no-change margin at 150 episodes per arm. In T4 the platform
  correctly produces no false regression, but it can never say "nothing changed" on this data.
- **No statement of how many more episodes would settle a question** (engine gap G-4). "Insufficient evidence"
  does not say how close you are.
- **No engine breakdown of why an outcome is unknown** (G-3); the platform derives reasons per episode only.
- **Defaults you can change but should know:** at least 30 known scenarios per arm, at least 5 failures across both
  arms together, a +-1 point margin around "no change". One task type per evaluation.

## The evidence we ship

- **MuJoCo is a simulation.** An idealised planar arm, no contact, encoder quantisation as the only sensor noise.
  The robot's "self-report" rule was written by us for the experiment. The 20 ms regression level was chosen on a
  separate pilot set (the 50 ms one was declared beforehand); the held-out seeds were never used to choose
  anything. The experiment was pre-registered before the held-out run (`examples/mujoco-regression/`).
- **CoreSense is real, but it is not a release comparison.** The dataset names no software revision, so the two
  "releases" are flight *conditions* of the same software. The 0.20 m arrival tolerance is Aerostack2's default,
  not the flights' (unpublished) setting. The motion-capture pose that verifies a claim also feeds the drone's
  controller, so the reference is not fully independent. The failures were induced by the experimenters. 35
  waypoints per condition, GoTo goals only. Times are one assumed host clock.
- **Neither dataset is from a deployed system.** No production data has been through the platform.

## Getting your own data in

- **Input is CSV or JSONL**, described by a hand-written JSON mapping (`pap.mapping/1`). There is no mapping
  editor and no schema inference. ROS bags, MCAP and LeRobot datasets are not ingested directly: the CoreSense
  example needed a separate extraction script (about 150 lines, reusing OpenMHS's rosbag2 reader).
- **The platform does not create ground truth.** If your data has no independent measurement, outcomes are
  "reported only" and no verdict about reality is possible. A contract is a set of simple conditions (equal,
  less/greater than, between, in) on measurements around the robot's claim.
- Uploads are limited to 100 MB per file by default; archives are refused.

## The installation you are trying

- **The trial uses the development identity**: you type any name to sign in. It listens on 127.0.0.1 only, for one
  person. A shared installation needs OIDC sign-in, which we have tested only against a local test provider, not
  Keycloak, Entra ID or Okta. Sessions end when the access token expires (at most 8 hours; no refresh); signing out
  does not end your session at the identity provider.
- Verified on a clean GitHub Linux runner and on Windows (local stack). Docker Desktop on Windows or macOS, and
  non-Chromium browsers, are untested.
- Not in the product: backup and restore tooling, the metrics and tracing stack (the application emits JSON logs,
  Prometheus metrics and OpenTelemetry traces, but no collector or dashboards ship with it), and the **Fleet,
  Incidents, Verification, Evidence and Integrations pages, which are placeholders** marked "Soon".
- Object storage: local volume, or S3 (tested against SeaweedFS only). Not tested against AWS S3, MinIO or others.
- Performance has been measured at 300 episodes (a verdict in about 10 seconds, one engine process per episode),
  not at tens of thousands.
- The engine is pinned to one OpenMHS commit. Release builds of the engine are not bit-identical across machines,
  so each platform records its own binary digest.

## About this trial itself

- **No external engineer has used this yet.** Everything in `trial/` is our own preparation; nothing in it is user
  feedback. The dry run in `DRY_RUN.md` is us following our own instructions and says so.
- The repository is private. Access is arranged by its owner; nothing in the trial needs our credentials once you
  have the code. Building the images downloads base images and packages (and the engine source from its public
  GitHub repository); the running system sends nothing anywhere: there is no telemetry, and traces leave only if
  you configure an OpenTelemetry endpoint yourself.

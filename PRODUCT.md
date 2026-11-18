# Product

## One sentence

Evidence-backed answers to "did this release make the robot better or worse, and can we prove what
actually happened?", for teams shipping robot software and learned policies into production.

## Who it is for (hypothesis until a real team confirms it)

Engineering teams that already run robots or policies repeatedly and record what happens:

- mobile manipulation and pick-and-place teams (warehouse, lab automation),
- teams training and deploying learned policies (imitation learning, VLA models),
- university and research fleets that compare controller or policy versions.

They already have logs, rosbags/MCAP, evaluation rollouts or CSV exports. What they lack is a trustworthy
answer to the release question that separates what the robot *said* from what independent evidence
*shows*, and says honestly when the data cannot decide.

**Validated so far: nothing with an external customer.** OpenMHS has been exercised on real recordings
(CoreSense drone flights, CC BY 4.0), Gazebo simulation and LeRobot PushT rollouts (simulation). The first
commercial goal is one external robotics team with a measurable release or outcome-verification problem.

## Questions the product answers

1. Did the robot actually complete its task? (reported vs independently verified outcome)
2. Can the reported success be independently verified? (verdict + reasons, or "unknown" and why)
3. Did the candidate release regress against the baseline? (engine verdict: regression, improvement,
   no_change, insufficient_evidence, with intervals)
4. Which scenarios, sites and robots are affected? (strata, paired scenarios, episode drill-down)
5. Is the evidence sufficient for a deployment decision? (sample counts, unknown bounds, warnings)

## First workflow: Release Intelligence

Organization → project → robots/sites → baseline and candidate releases → upload evidence for each →
apply a versioned mapping → evaluation job (OpenMHS verifies outcomes and compares releases) → comparison
with uncertainty and warnings → episode drill-down → exported HTML and JSON report.

Nothing else is built until this works end to end against the real engine.

## Commercial boundaries

| Open source (OpenMHS) | Commercial platform (this repo) |
|---|---|
| Event and evidence formats, outcome verifier, release statistics, local store, importers | Multi-user workspaces, history of evaluations, evidence management, dashboards, reports, identity, governance, self-hosted then managed deployment |

Initial revenue model: paid release audits (we run the platform on a team's evidence), converting recurring
needs into self-hosted enterprise deployments. Not pursued now: hobbyist tiers, billing, marketplaces,
consumer acquisition.

## Product principles

- **Honest by construction.** Unknown is shown. Missing evidence is never counted as success.
  "Insufficient evidence" is a valid and common answer.
- **Descriptive vs inferential.** Rates and counts are descriptive; regression/improvement claims come only
  from the engine's inferential verdict with its stated rules.
- **Provenance everywhere.** Every number traces to input checksums, the mapping revision and the engine
  version that produced it.
- **Vendor-neutral and observation-only.** We read what robots record; we never drive robots.

## Deferred (labelled "not yet available" in the interface)

Fleet Intelligence, Incident Intelligence (beyond incidents shown inside a comparison), Evaluation CI
integration, HIL test intelligence, enterprise governance beyond RBAC + audit log, managed integrations
(Open-RMF, OPC UA, Isaac Sim, MuJoCo, warehouse systems), signed evidence manifests, Rerun-based replay.

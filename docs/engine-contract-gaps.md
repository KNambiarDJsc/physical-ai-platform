# OpenMHS interface gaps

Requests for changes in OpenMHS that the platform would benefit from. Nothing here is implemented by
editing OpenMHS from this repository; each item is a proposal for the OpenMHS maintainers (the same owner).

## G-1 No versioned machine interface besides the CLI
`ops` and `outcome` are reachable only through the CLI. The JSON shapes are serde-derived structs without a
published schema or version field (except `rules_version` on comparisons and `verifier` on reports).
**Ask:** JSON Schemas for `Comparison`, `IncidentSummary`, `IncidentDetail`, ingest result and verifier
report, with a schema version field. **Meanwhile:** the bridge validates the fields it uses with Pydantic
models and fails loudly on drift; the bridge integration tests pin the shapes to commit `e9ef873`.

## G-2 Building `outcome.verified.conditions` from a verifier report is importer-internal
`conditions_of` lives in `python/openmhs/importers/coresense_verify.py`. **Ask:** have
`outcome verify` emit an event-ready `conditions` block (or publish the helper). **Meanwhile:** a copied
helper with a parity test (decision D-008).

## G-3 No engine-native per-arm unknown-reason breakdown
`ops compare` counts unknowns but does not say why (evidence missing vs conflicting vs stale). The
platform derives this per episode from verifier reasons and shows counts descriptively. **Ask:** a
per-arm `unknown_reasons` map in `Arm`.

## G-4 No statement of minimum detectable effect
With `insufficient_evidence` the engine says how many known outcomes are missing for its rule, not what
effect size the current sample could detect. Users will ask "how many more runs do I need?".
**Ask:** an optional power/MDE estimate with its method named. Until then the platform shows only the
engine's reasons and does not compute one (directive: no statistics outside the engine).

## G-5 Timeouts and cancellation are process-level only
Long `ops ingest` runs cannot be cancelled cooperatively; the bridge kills the process and discards the
per-job store. Acceptable because stores are per job and rebuildable.

## G-6 Correlated attempts beyond scenario ids
The engine treats attempts sharing `scenario_id` as replicates and supports pairing by scenario. Other
correlation (same robot on the same day, same object instance) is not modelled. The platform must warn
when one robot or one site dominates an arm; such warnings are descriptive and labelled as ours.

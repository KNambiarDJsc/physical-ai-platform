# Graph Report - physical-ai-platform  (2026-11-23)

## Corpus Check
- 407 files · ~379,829 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 31 file(s) not represented in the graph (top: .stl 10, (none) 6, .lock 4)

## Summary
- 4353 nodes · 11582 edges · 234 communities (190 shown, 44 thin omitted)
- Extraction: 94% EXTRACTED · 6% INFERRED · 0% AMBIGUOUS · INFERRED: 687 edges (avg confidence: 0.93)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `93caa48b`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [project]/page.tsx
- test_pipeline_real.py
- evaluations/routes.py
- auth.ts
- Decisions
- organizations/routes.py
- deps.py
- fixture
- typing
- test_auth.py
- Communities (220 total, 42 thin omitted)
- ok
- ._run
- get_settings
- openmhs_bridge/__init__.py
- package.json
- evidence/routes.py
- Engine
- test_storage_s3.py
- openamr-cmd-timeout/build.py
- episode.py
- failure-paths.spec.ts
- subprocess
- compilerOptions
- test_twin_models.py
- test_mapping.py
- as_user
- observability/__init__.py
- check_features.py
- docker-compose.yml
- argparse
- releases.py
- experiments.ts
- pytest
- postgres
- Scene.tsx
- Twin.tsx
- worker
- ingestion/mapping.py
- test_things_server.py
- contracts/mapping.py
- twin/routes.py
- test_isolation.py
- experiments/routes.py
- rules
- Scene.tsx
- api
- web
- environment
- schema.d.ts
- ci.yml
- hashlib
- pap_sim_host/server.py
- test_agent_tools.py
- api
- AppShell.tsx
- test_twin_recordings.py
- migrate
- modules.spec.ts
- scripts
- steps
- Physical AI Reliability Platform: instructions for coding sessions
- hooks
- with
- Product
- Rules for any coding agent working in this repository
- env
- json
- generate.py
- verify.sh
- context
- path
- check_observability.py
- Blockers, open dependencies and known failures
- Progress
- create_project
- smoke.sh
- pathlib
- workflows/routes.py
- x-hardening
- Onboarding a team
- OpenMHS capability audit (CORE-001)
- security
- verify
- on
- build-openmhs.sh
- pap_virtual_lab/server.py
- loop.sh
- postcss.config.mjs
- pap-api
- get-seaweedfs.sh
- physical-ai-platform
- Evaluation form
- test_experiments.py
- spec.py
- test_things_server.py
- hardware/routes.py
- agent.py
- @playwright/test
- collections_abc
- WotHttpAdapter
- tools.py
- Observer
- error
- main.py
- test_observability.py
- sim.py
- test_harness.py
- test_workflows.py
- platform_run.py
- Toolbox
- PlatformClient
- wot.py
- re
- test_sim_host.py
- pap_agent_harness/__main__.py
- CappedModel
- node.py
- math
- Pre-registration: controlled regression experiment (Milestone C)
- outputs
- testing.py
- Design: Precision Industrial
- otel-collector.yaml
- tests_ros/conftest.py
- Host
- .run_scenario
- os
- hub_motor_wheel
- evaluations/service.py
- Bundled third-party assets
- castor
- nodes
- trial-exercise.spec.ts
- generated_by
- assistant.py
- Simulation execution and Experiment Studio
- model.py
- catalog.py
- Trace
- source
- TopicTracker
- Architecture
- Observation.tsx
- Open-source integration registry
- Real robot evidence: CoreSense drone flights (Milestone B)
- inputs
- oidc-provider.mjs
- Any
- test_model.py
- make_handler
- prometheus
- OpenMHS interface gaps
- base_camera
- base_chassis
- base_covers
- base_equipment
- caster
- motor_driver
- hub_motor_wheel
- imu
- lidar
- tof
- ultrasonic
- Handoff to Codex: Physical AI Platform (2026-11-23)
- scrape_configs
- healthcheck
- virtual-lab
- x-api-env
- Agentic harness (HAR-001)
- base_link_frame
- test_storage_s3.py
- explain_event
- JointTracker
- start.sh
- test_scaffold.py
- run_session
- step_check
- ros_stack.sh
- investigate.py
- ClockTracker
- ros_stack_wsl.sh
- Design audit, 2026-11-21 (Impeccable `audit`, web)
- budgets
- eslint.config.mjs
- run_main.sh
- run_scenario.sh
- compose
- trial
- test_the_platform_checks_the_digest_itself_when_a_host_serves_other_bytes
- dry_run.sh
- test_links_outside_the_configured_endpoint_are_refused
- install-design-skills.sh
- test_ros_workspace.py
- openamr-cmd-timeout/README.md
- observability/README.md
- Tool
- pap-sim-host
- pap-virtual-lab
- time
- csv
- Graph Report - physical-ai-platform  (2026-11-23)
- Prompt for Codex (paste this as the first message)
- Session handoff (2026-11-23)
- extract.py
- Prompt for the next Claude session (paste as the first message)
- pg.py
- test_trial_baseline.py
- JobStateCollector
- grounding.py
- env.py
- SyringePump
- engine_observer
- demo_up.sh

## God Nodes (most connected - your core abstractions)
1. `Communities (220 total, 42 thin omitted)` - 179 edges
2. `ok()` - 95 edges
3. `as_user()` - 77 edges
4. `api()` - 68 edges
5. `error()` - 67 edges
6. `Notice()` - 56 edges
7. `get_settings()` - 53 edges
8. `session_factory()` - 49 edges
9. `Environment` - 49 edges
10. `make_org()` - 48 edges

## Surprising Connections (you probably didn't know these)
- `Operations` --references--> `api()`  [INFERRED]
  docs/deployment.md → apps/web/src/lib/api/client.ts
- `What runs` --references--> `api()`  [INFERRED]
  docs/deployment.md → apps/web/src/lib/api/client.ts
- `2026-11-18 — Session 1: harness, engine audit, pinned bridge` --references--> `Result`  [INFERRED]
  harness/progress.md → packages/openmhs-bridge/src/openmhs_bridge/engine.py
- `Suggested Questions` --references--> `Host`  [INFERRED]
  docs/handoff/graphify/GRAPH_REPORT.md → runtimes/sim-host/src/pap_sim_host/runner.py
- `2026-11-22 - Session 8 (later): Simulation Experiment Studio started (SIM-001..006), handoff` --references--> `error()`  [INFERRED]
  harness/progress.md → services/api/app/auth/deps.py

## Import Cycles
- None detected.

## Communities (234 total, 44 thin omitted)

### Community 0 - "[project]/page.tsx"
Cohesion: 0.05
Nodes (93): Page(), Page(), Page(), Page(), Episodes(), EpisodesPage(), Params, Evaluation() (+85 more)

### Community 1 - "test_pipeline_real.py"
Cohesion: 0.14
Nodes (16): demo_input(), main(), outcome_class(), PipelineError, run_pipeline(), result(), test_deterministic(), test_engine_accepted_every_event() (+8 more)

### Community 2 - "evaluations/routes.py"
Cohesion: 0.08
Nodes (36): EvaluationResult, build_report(), _comparison(), _e(), _interval(), _pct(), _pp(), render_html() (+28 more)

### Community 3 - "auth.ts"
Cohesion: 0.09
Nodes (42): KEYS, offered, openDevice(), orgOf(), run, apiBase(), DROP_RESPONSE, dynamic (+34 more)

### Community 4 - "Decisions"
Cohesion: 0.05
Nodes (39): D-001 (2026-11-18) Repository on D:, separate from OpenMHS and AI Studio, D-002 (2026-11-18) Engine boundary = the OpenMHS CLI with `--json`, pinned by commit and binary SHA-256, D-003 (2026-11-18) One engine store per evaluation job, D-004 (2026-11-18) Verdicts per episode via `openmhs outcome verify`, statistics via `ops compare`, D-005 (2026-11-18) Job queue: own table with SKIP LOCKED, not Procrastinate (for now), D-006 (2026-11-18) Python 3.12 for the API; pgserver as a dev-only PostgreSQL, D-007 (2026-11-18) OIDC validation with PyJWT, not Authlib, D-009 (2026-11-18) Split the web scaffold out of INF-002 into WEB-001 (+31 more)

### Community 5 - "organizations/routes.py"
Cohesion: 0.10
Nodes (21): AuditOut, create_credential(), create_org(), _cred(), CredentialCreated, CredentialIn, CredentialOut, delete_member() (+13 more)

### Community 6 - "deps.py"
Cohesion: 0.11
Nodes (18): _action(), _deny(), error(), get_principal(), org_context(), Principal, _project(), project_engineer() (+10 more)

### Community 7 - "fixture"
Cohesion: 0.07
Nodes (23): Before you start, Demo runbook (about 12 minutes), The story, Walkthrough, What to say, and not say, God Nodes (most connected - your core abstractions), fixture(), main() (+15 more)

### Community 8 - "typing"
Cohesion: 0.08
Nodes (25): AuditEvent, record(), User, Base, CreatedMixin, IdMixin, EpisodeRecord, JobArtifact (+17 more)

### Community 9 - "test_auth.py"
Cohesion: 0.11
Nodes (18): add_member(), bearer(), make_org(), _b64(), hs256_confusion(), idp(), _Keys, oidc_client() (+10 more)

### Community 10 - "Communities (220 total, 42 thin omitted)"
Cohesion: 0.01
Nodes (178): Communities (220 total, 42 thin omitted), Community 0 - "[project]/page.tsx", Community 105 - "Evaluation form", Community 106 - "test_experiments.py", Community 107 - "spec.py", Community 108 - "test_things_server.py", Community 109 - "hardware/routes.py", Community 10 - "spec.py" (+170 more)

### Community 11 - "ok"
Cohesion: 0.41
Nodes (8): connect(), lab_org(), test_a_device_that_disappears_is_kept_and_marked_missing(), test_an_environment_the_operator_withdrew_is_unavailable(), test_discovery_records_devices_capabilities_and_digests(), test_only_operator_environments_can_be_connected(), test_properties_are_read_live(), test_roles_and_a_physical_environment_is_still_observable()

### Community 12 - "._run"
Cohesion: 0.13
Nodes (5): Invocation, RawRun, Result, EngineError, test_unknown_error_code_is_a_programming_error()

### Community 13 - "get_settings"
Cohesion: 0.07
Nodes (24): get_settings(), session_factory(), get_engine(), EvaluationJob, get_storage(), _s3(), capture_ready(), capture_trial() (+16 more)

### Community 14 - "openmhs_bridge/__init__.py"
Cohesion: 0.18
Nodes (15): G-1 No versioned machine interface besides the CLI, Arm, Comparison, ConditionResult, EngineProvenance, IncidentDetail, IncidentSummary, IngestResult (+7 more)

### Community 15 - "package.json"
Cohesion: 0.07
Nodes (36): devDependencies, eslint@9.39.5, eslint-config-next@15.5.29, jsdom@26.1.0, openapi-typescript@7.13.0, tailwindcss@4.3.5, @tailwindcss/postcss@4.3.5, @testing-library/jest-dom@6.6.3 (+28 more)

### Community 16 - "evidence/routes.py"
Cohesion: 0.14
Nodes (8): Artifact, ArtifactOut, _chunks(), display_name(), get_artifact(), list_artifacts(), out(), upload()

### Community 17 - "Engine"
Cohesion: 0.17
Nodes (15): Engine, _load_conditions_of(), records(), test_a_different_digest_is_refused(), test_gazebo_ab_verified_comparison_is_reproduced(), test_hostile_release_labels_stay_values(), test_malformed_contract_is_an_input_error(), test_observers_see_every_engine_process() (+7 more)

### Community 18 - "test_storage_s3.py"
Cohesion: 0.12
Nodes (16): chunks(), key_for(), LocalStorage, S3Storage, TooLarge, _verified(), proj(), stored_files() (+8 more)

### Community 19 - "openamr-cmd-timeout/build.py"
Cohesion: 0.20
Nodes (8): do_build(), do_import(), find(), load(), render(), rows(), sha256(), main()

### Community 20 - "episode.py"
Cohesion: 0.12
Nodes (10): Episode, EpisodeContext, Field_, main(), render(), unavailable(), test_committed_schemas_match_the_models(), test_episode_cannot_omit_context_or_provenance() (+2 more)

### Community 21 - "failure-paths.spec.ts"
Cohesion: 0.20
Nodes (6): DEMO, fillEvaluation(), ids, pick(), ROOT, run

### Community 22 - "subprocess"
Cohesion: 0.10
Nodes (16): build(), check(), git(), main(), sha(), files(), main(), main() (+8 more)

### Community 23 - "compilerOptions"
Cohesion: 0.09
Nodes (21): compilerOptions, allowJs, esModuleInterop, incremental, isolatedModules, jsx, lib, module (+13 more)

### Community 24 - "test_twin_models.py"
Cohesion: 0.30
Nodes (13): pipeline_then_cancel(), post_model(), real(), refused(), setup(), sha(), stl(), synthetic() (+5 more)

### Community 25 - "test_mapping.py"
Cohesion: 0.17
Nodes (18): MappingSpec, verifier_input(), jsonl_spec(), run(), spec(), test_artifact_level_problems_reject_the_whole_artifact(), test_bad_cells_reject_the_row(), test_blank_measurement_produces_no_record() (+10 more)

### Community 26 - "as_user"
Cohesion: 0.16
Nodes (20): as_user(), submit(), test_cancel_during_the_last_stage_is_not_saved_as_success(), test_cancel_queued(), test_cancel_running_kills_the_engine(), test_concurrent_workers_never_claim_the_same_job(), test_full_evaluation(), test_invalid_submissions() (+12 more)

### Community 28 - "check_features.py"
Cohesion: 0.47
Nodes (4): check(), visit(), eligible(), main()

### Community 29 - "docker-compose.yml"
Cohesion: 0.08
Nodes (23): name, cap_drop, command, expose, image, profiles, read_only, restart (+15 more)

### Community 30 - "argparse"
Cohesion: 0.13
Nodes (9): D-037 (2026-11-22) Experiment specs pin what can change underneath them; approval names a checksum, main(), run(), main(), seed(), Seeder, check(), main() (+1 more)

### Community 31 - "releases.py"
Cohesion: 0.12
Nodes (19): _artifact(), _iso(), judge_as_releases(), _mapping(), mapping_for(), _release(), to_csv(), trial_rows() (+11 more)

### Community 32 - "experiments.ts"
Cohesion: 0.05
Nodes (111): Page(), Crumbs(), ErrorNotice(), explain(), Help, ModelChoice, Progress(), SimulatedBadge() (+103 more)

### Community 33 - "pytest"
Cohesion: 0.15
Nodes (12): EngineConfig, engine_from_env(), python_engine(), test_arguments_reach_the_process_verbatim_without_a_shell(), test_cancel_kills_the_process(), test_digest_mismatch_is_refused_before_running(), test_invalid_output_is_a_structured_error(), test_missing_binary() (+4 more)

### Community 34 - "postgres"
Cohesion: 0.22
Nodes (9): POSTGRES_DB, POSTGRES_PASSWORD, POSTGRES_USER, environment, image, restart, security_opt, volumes (+1 more)

### Community 35 - "Scene.tsx"
Cohesion: 0.21
Nodes (10): Boundary, Controls(), linkOf(), Robot(), RobotProps, Scene(), SceneProps, SceneStatus (+2 more)

### Community 36 - "Twin.tsx"
Cohesion: 0.06
Nodes (67): Page(), Assistant(), Explanation, Finding, TONE, f(), Inspector(), Tab (+59 more)

### Community 37 - "worker"
Cohesion: 0.13
Nodes (15): worker, cap_drop, command, cpus, expose, image, mem_limit, memswap_limit (+7 more)

### Community 38 - "ingestion/mapping.py"
Cohesion: 0.21
Nodes (16): SourceLocator, Source, TimeSource, apply_mapping(), ArtifactRejected, _cell(), _decode(), _get() (+8 more)

### Community 39 - "test_things_server.py"
Cohesion: 0.22
Nodes (10): call(), code(), readers(), test_no_thing_description_declares_an_action(), test_only_get_and_head_are_served(), test_parse_td_of_a_thing_with_no_properties_still_has_no_actions(), test_the_observer_has_no_means_to_command_a_robot(), test_the_only_client_is_the_list_controllers_query() (+2 more)

### Community 40 - "contracts/mapping.py"
Cohesion: 0.26
Nodes (7): Condition, ContractTemplate, InputSpec, Measurement, MissingData, ReportedOutcome, _Strict

### Community 41 - "twin/routes.py"
Cohesion: 0.07
Nodes (36): _canonical(), create_model_version(), create_recording(), _episode_link(), EpisodeLink, FileOut, FileRef, get_model_file() (+28 more)

### Community 42 - "test_isolation.py"
Cohesion: 0.18
Nodes (9): register(), bodies(), _call(), org_routes(), test_every_route_with_a_body_has_one_here(), test_me_lists_only_own_organizations(), test_outsiders_cannot_reach_the_victim(), _toy() (+1 more)

### Community 43 - "experiments/routes.py"
Cohesion: 0.05
Nodes (70): OrgContext, _capture(), workflow_slug(), check_model(), Listing, scenario_digest(), _schema_errors(), simulator_ref() (+62 more)

### Community 44 - "rules"
Cohesion: 0.14
Nodes (13): exclude, pattern, pattern, pattern-not, rules, id, languages, message (+5 more)

### Community 45 - "Scene.tsx"
Cohesion: 0.11
Nodes (18): dependencies, clsx@2.1.1, echarts@6.1.0, lucide-react@1.75.0, next@15.5.29, openid-client@6.8.9, react@19.2.0, react-dom@19.2.0 (+10 more)

### Community 46 - "api"
Cohesion: 0.15
Nodes (13): cap_drop, depends_on, image, ports, read_only, restart, security_opt, tmpfs (+5 more)

### Community 47 - "web"
Cohesion: 0.15
Nodes (13): condition, api, PAP_API_URL, web, cap_drop, depends_on, environment, image (+5 more)

### Community 48 - "environment"
Cohesion: 0.27
Nodes (14): environment, OTEL_EXPORTER_OTLP_ENDPOINT, PAP_AUTH_MODE, PAP_DATABASE_URL, PAP_ENGINE_TIMEOUT_S, PAP_ENV, PAP_ENVIRONMENTS, PAP_JOB_MAX_ATTEMPTS (+6 more)

### Community 49 - "schema.d.ts"
Cohesion: 0.17
Nodes (9): components, $defs, operations, paths, webhooks, Engineering loop (one feature, one iteration), RFC-0004, RFC-0005 (+1 more)

### Community 50 - "ci.yml"
Cohesion: 0.25
Nodes (7): concurrency, cancel-in-progress, group, jobs, name, permissions, contents

### Community 51 - "hashlib"
Cohesion: 0.30
Nodes (7): canonical_json(), _check(), digest(), sha256_bytes(), sha256_file(), sha256_text(), test_canonical_json_sorts_keys_and_matches_the_engine_rules()

### Community 52 - "pap_sim_host/server.py"
Cohesion: 0.15
Nodes (5): create_server(), main(), configure(), create_server(), main()

### Community 53 - "test_agent_tools.py"
Cohesion: 0.22
Nodes (11): api_url(), contradiction_run(), Mcp, test_a_contradiction_is_investigated_with_findings_that_cite_stored_evidence(), test_a_proposal_in_a_physical_environment_cannot_be_approved(), test_a_viewer_can_propose_but_never_approve_and_an_engineer_approval_runs_through_the_executor(), test_bad_input_unknown_tools_and_methods_are_answered_not_crashed(), test_the_tool_list_is_exactly_the_allowlist_with_typed_schemas_and_honest_hints() (+3 more)

### Community 54 - "api"
Cohesion: 0.11
Nodes (60): Notice(), DeviceBrowser(), Environments(), Hardware(), KindBadge(), useCatalog(), useDiscover(), Member (+52 more)

### Community 55 - "AppShell.tsx"
Cohesion: 0.06
Nodes (55): config, geist@1.7.2, Page(), metadata, RootLayout(), Page(), Overview(), Providers() (+47 more)

### Community 56 - "test_twin_recordings.py"
Cohesion: 0.12
Nodes (28): decode(), _after_last_command(), build_track(), at(), canonical(), changes(), _cols(), _events() (+20 more)

### Community 57 - "migrate"
Cohesion: 0.18
Nodes (11): postgres, cap_drop, command, depends_on, image, read_only, restart, security_opt (+3 more)

### Community 58 - "modules.spec.ts"
Cohesion: 0.12
Nodes (8): run, EXPECTED, MJ, ROOT, run, DEMO, run, snap

### Community 59 - "scripts"
Cohesion: 0.20
Nodes (10): scripts, build, check:api, dev, e2e, gen:api, lint, start (+2 more)

### Community 60 - "steps"
Cohesion: 0.35
Nodes (11): steps, COMPOSE_BAKE, PAP_SKIP_WEB_BUILD, steps, env, if, name, run (+3 more)

### Community 61 - "Physical AI Reliability Platform: instructions for coding sessions"
Cohesion: 0.22
Nodes (8): Commands, End of every session (or context window), Graphify (optional), Invariants (do not break, do not work around), Machine constraints (this workstation), Physical AI Reliability Platform: instructions for coding sessions, Start of every session, Writing

### Community 62 - "hooks"
Cohesion: 0.22
Nodes (8): hooks, PostToolUse, PreToolUse, Stop, permissions, allow, deny, $schema

### Community 63 - "with"
Cohesion: 0.22
Nodes (9): with, cache, cache-dependency-path, fetch-depth, name, node-version, path, retention-days (+1 more)

### Community 64 - "Product"
Cohesion: 0.22
Nodes (8): Commercial boundaries, Deferred (labelled "not yet available" in the interface), First workflow: Release Intelligence, One sentence, Product, Product principles, Questions the product answers, Who it is for (hypothesis until a real team confirms it)

### Community 65 - "Rules for any coding agent working in this repository"
Cohesion: 0.25
Nodes (7): Boundaries, Evidence, Hand-off, Handoff (start here if you are new, including Codex), Rules for any coding agent working in this repository, Safety, Scope

### Community 66 - "env"
Cohesion: 0.29
Nodes (7): env, GITLEAKS_IMAGE, NODE_VERSION, RUST_TOOLCHAIN, SEMGREP_IMAGE, TRIVY_IMAGE, UV_VERSION

### Community 67 - "json"
Cohesion: 0.07
Nodes (26): main(), main(), engine(), fixtures(), pinned_src(), _unavailable(), main(), render() (+18 more)

### Community 68 - "generate.py"
Cohesion: 0.22
Nodes (3): run(), _stamp(), main()

### Community 69 - "verify.sh"
Cohesion: 0.62
Nodes (6): absent(), python_gates(), verify.sh script, step(), UV_CACHE_DIR, web_gates()

### Community 70 - "context"
Cohesion: 0.48
Nodes (7): build, context, dockerfile, build, build, build, build

### Community 71 - "path"
Cohesion: 0.53
Nodes (6): env_file, path, required, env_file, env_file, env_file

### Community 72 - "check_observability.py"
Cohesion: 0.12
Nodes (8): main(), prom(), wait(), discover_jwks_url(), issuer_url_allowed(), OidcVerifier, TokenInvalid, verifier()

### Community 73 - "Blockers, open dependencies and known failures"
Cohesion: 0.29
Nodes (6): B-001 Docker engine not running on the development workstation, B-002 No external customer data, B-003 Graphify project install awaits review, B-004 Live OIDC provider not exercised, B-005 Real-model harness verification needs provider configuration and authorization, Blockers, open dependencies and known failures

### Community 74 - "Progress"
Cohesion: 0.08
Nodes (22): 2026-11-18 — Session 1 (continued): the first real Release Intelligence workflow runs end to end in the API, 2026-11-18 — Session 1: harness, engine audit, pinned bridge, 2026-11-18 — Session 1 (later): web application and the first browser-verified end-to-end flow, 2026-11-18 — Session 2: reports, failure-path e2e and the smoke script, 2026-11-19 — Session 3: deployment validation on CI, first real robot evidence, 2026-11-19 — Session 4: Milestone D, trial pack for an independent engineer, 2026-11-21 — Session 5: module pages, design system and application shell, 2026-11-21 — Session 6: design-system checkpoint closed; infrastructure started (+14 more)

### Community 75 - "create_project"
Cohesion: 0.23
Nodes (6): create_project(), get_project(), list_projects(), out(), ProjectIn, ProjectOut

### Community 76 - "smoke.sh"
Cohesion: 0.40
Nodes (4): dc(), smoke.sh script, TEMP, TMPDIR

### Community 77 - "pathlib"
Cohesion: 0.14
Nodes (18): release(), EvaluationConfig, ArtifactInput, config_digest(), EpisodeResult, _events(), PipelineInput, PipelineOutput (+10 more)

### Community 78 - "workflows/routes.py"
Cohesion: 0.16
Nodes (18): definition_sha256(), Workflow, create_workflow(), get_run(), get_workflow(), list_runs(), list_templates(), list_workflows() (+10 more)

### Community 79 - "x-hardening"
Cohesion: 0.40
Nodes (5): x-hardening, cap_drop, read_only, security_opt, tmpfs

### Community 80 - "Onboarding a team"
Cohesion: 0.07
Nodes (25): Configuration, Deploying the platform, Environment catalog (what workspaces may connect), Install, Operations, Security checklist, What runs, Engineering handoff (+17 more)

### Community 81 - "OpenMHS capability audit (CORE-001)"
Cohesion: 0.50
Nodes (3): Not re-run here, OpenMHS capability audit (CORE-001), What the platform depends on

### Community 82 - "security"
Cohesion: 0.50
Nodes (4): security, name, runs-on, timeout-minutes

### Community 83 - "verify"
Cohesion: 0.50
Nodes (4): verify, name, runs-on, timeout-minutes

### Community 84 - "on"
Cohesion: 0.50
Nodes (4): on, pull_request, push, branches

### Community 85 - "build-openmhs.sh"
Cohesion: 0.67
Nodes (3): CARGO_TARGET_DIR, lock_field(), build-openmhs.sh script

### Community 86 - "pap_virtual_lab/server.py"
Cohesion: 0.07
Nodes (3): Bench, Balance, SimulationControl

### Community 91 - "pap-api"
Cohesion: 0.40
Nodes (5): openmhs-bridge, pap-agent-harness, pap-agent-tools, pap-api, pap-device-sdk

### Community 105 - "Evaluation form"
Cohesion: 0.04
Nodes (41): Dry run (ours, not an external user's), Not exercised, Problems found while preparing, Run 1: local Windows stack (not Compose), 2026-11-19, Run 2: clean GitHub runner, Docker, `bash trial/start.sh`, What was checked, Where the plain script is faster or simpler, Part A: with the platform (about 21 minutes) (+33 more)

### Community 106 - "test_experiments.py"
Cohesion: 0.14
Nodes (38): ok(), approved(), capture(), configure(), configure_env(), decide(), drive_spec(), checkout_status() (+30 more)

### Community 107 - "spec.py"
Cohesion: 0.08
Nodes (25): compile_trial(), _condition(), _evidence_name(), _operand(), Approval, Arm, canonical_json(), checksum() (+17 more)

### Community 108 - "test_things_server.py"
Cohesion: 0.14
Nodes (9): load(), replay_server(), serve(), build_things(), Property, Thing, server(), test_a_non_finite_value_is_sent_as_null_so_any_strict_parser_accepts_the_response() (+1 more)

### Community 109 - "hardware/routes.py"
Cohesion: 0.06
Nodes (38): EnvironmentConfig, Settings, host_device(), read_listing(), Capability, Device, Environment, CapabilityOut (+30 more)

### Community 110 - "agent.py"
Cohesion: 0.09
Nodes (4): _stop_cause(), BudgetExceeded, Ledger, StopSession

### Community 111 - "@playwright/test"
Cohesion: 0.08
Nodes (19): MJ, ROOT, run, run, run, run, EXP, MODEL (+11 more)

### Community 112 - "collections_abc"
Cohesion: 0.10
Nodes (10): upgrade(), upgrade(), upgrade(), upgrade(), upgrade(), upgrade(), upgrade(), _org_fk() (+2 more)

### Community 113 - "WotHttpAdapter"
Cohesion: 0.15
Nodes (10): AdapterError, _forms_href(), _problem(), WotHttpAdapter, Writable, rid(), test_a_fault_changes_what_happens_not_what_the_pump_reports(), test_actions_run_and_a_repeated_request_id_has_no_second_effect() (+2 more)

### Community 114 - "tools.py"
Cohesion: 0.15
Nodes (23): ComparisonIn, _devices(), EventIn, ExperimentIn, ExperimentRunIn, _experiments(), _explain(), _health() (+15 more)

### Community 115 - "Observer"
Cohesion: 0.15
Nodes (3): DiagnosticsTracker, Observer, _stamp()

### Community 116 - "error"
Cohesion: 0.20
Nodes (12): ExperimentProposal, approve(), DecisionIn, _get(), get_proposal(), list_proposals(), _out(), ProposalIn (+4 more)

### Community 117 - "main.py"
Cohesion: 0.13
Nodes (8): engine_status(), create_app(), healthz(), observe(), configure_tracing(), extract_context(), monotonic_ms(), test_metrics_are_closed_in_production()

### Community 118 - "test_observability.py"
Cohesion: 0.17
Nodes (7): JsonFormatter, redact(), logs(), spans(), test_log_lines_are_json_and_secrets_are_redacted(), test_one_trace_from_request_to_engine_with_json_logs(), test_request_ids_are_validated()

### Community 119 - "sim.py"
Cohesion: 0.14
Nodes (11): Config, environment(), episode(), fk(), ik(), initial_conditions(), main(), peak_rss_mb() (+3 more)

### Community 120 - "test_harness.py"
Cohesion: 0.18
Nodes (16): doc(), Platform, session(), test_a_session_persists_and_resumes_its_conversation(), test_a_session_reads_through_the_tools_and_answers_with_a_full_grounded_trace(), test_an_answer_citing_ids_no_tool_returned_is_flagged_as_unsupported(), test_an_approval_that_cannot_be_answered_is_a_refusal_not_a_failure(), test_an_experiment_budget_holds_across_sessions() (+8 more)

### Community 121 - "test_workflows.py"
Cohesion: 0.32
Nodes (14): get_run(), invocations(), lab(), lab_call(), run(), test_a_blocked_line_is_a_contradiction_reported_success_verified_violated(), test_a_healthy_dispense_is_verified_by_the_engine(), test_a_killed_worker_process_is_replaced_and_every_dispense_happens_once() (+6 more)

### Community 122 - "platform_run.py"
Cohesion: 0.19
Nodes (11): checkout_state(), collect(), Failed, main(), preflight(), read_json(), Refused, repair_checkout() (+3 more)

### Community 123 - "Toolbox"
Cohesion: 0.14
Nodes (10): platform_tools(), make(), _experiments(), FastPath, _run_status(), try_fast_path(), _verdicts(), Cancelled (+2 more)

### Community 124 - "PlatformClient"
Cohesion: 0.15
Nodes (9): PlatformClient, ToolError, main(), call(), handle(), serve(), tool_listing(), test_only_the_implemented_protocol_version_is_negotiated() (+1 more)

### Community 125 - "wot.py"
Cohesion: 0.19
Nodes (6): DeviceAdapter, Affordance, DiscoveredDevice, Invocation, parse_td(), td_digest()

### Community 126 - "re"
Cohesion: 0.15
Nodes (14): by_name(), test_connectivity_describes_the_observer_process(), test_controllers_match_the_controller_manager(), test_diagnostics_match_what_the_controller_manager_publishes(), test_expected_topics_report_what_the_graph_does_and_does_not_publish(), test_joint_states_match_a_cli_echo(), test_nodes_match_ros2_node_list(), test_real_staleness_when_the_publisher_really_stops() (+6 more)

### Community 127 - "test_sim_host.py"
Cohesion: 0.16
Nodes (14): adapter(), host(), rid(), run(), test_a_catalog_whose_command_names_an_undeclared_parameter_is_refused_at_start(), test_a_repeated_request_id_returns_the_stored_result_and_runs_nothing(), test_a_run_returns_exactly_what_the_scenario_measured_and_left_with_verifiable_artifacts(), test_failures_are_failures_never_a_made_up_success() (+6 more)

### Community 128 - "pap_agent_harness/__main__.py"
Cohesion: 0.15
Nodes (10): Options, LLMSettings, NotConfigured, _confirm(), main(), _progress(), utf8_streams(), build_model() (+2 more)

### Community 129 - "CappedModel"
Cohesion: 0.16
Nodes (3): CappedModel, ScriptedModel, _usage()

### Community 130 - "node.py"
Cohesion: 0.14
Nodes (5): load_profile(), main(), check_expected(), ExpectedTopic, run()

### Community 131 - "math"
Cohesion: 0.40
Nodes (6): by_scenario(), compare(), main(), mcnemar_exact(), newcombe(), wilson()

### Community 132 - "Pre-registration: controlled regression experiment (Milestone C)"
Cohesion: 0.11
Nodes (17): Analysis (all statistics by the pinned engine; no separate statistics in Python), Groups, Pilot (seeds 900000-900029, never reused), Pre-registration: controlled regression experiment (Milestone C), Predictions, recorded before running, Question, Resource limits, Sample size (+9 more)

### Community 133 - "outputs"
Cohesion: 0.11
Nodes (18): corrections, instance, origin_set_mm, origin_was_mm, reason, substituted_by, licence, chassis_meshes (+10 more)

### Community 134 - "testing.py"
Cohesion: 0.26
Nodes (6): free_port(), run_sim_host(), run_virtual_lab(), _serve(), _uv(), lab()

### Community 135 - "Design: Precision Industrial"
Cohesion: 0.11
Nodes (17): 10. Motion, 11. Accessibility, 12. Anti-patterns (reject in review), 1. Honesty rules come first, 2. Colour tokens, 3. Typography, 4. Spacing, shape, elevation, 5. Application shell (+9 more)

### Community 136 - "otel-collector.yaml"
Cohesion: 0.11
Nodes (17): timeout, verbosity, exporters, debug, endpoint, protocols, traces, processors (+9 more)

### Community 137 - "tests_ros/conftest.py"
Cohesion: 0.19
Nodes (9): eventually(), free_port(), have_ros(), kill_tree(), Obs, pytest_collection_modifyitems(), run(), sh() (+1 more)

### Community 138 - "Host"
Cohesion: 0.20
Nodes (5): Scenario, Host, HostError, _sha256(), _tail()

### Community 140 - "os"
Cohesion: 0.25
Nodes (9): bag(), record(), summary(), test_a_real_freeze_shows_up_as_a_listed_stale_interval_and_is_not_interpolated(), test_counts_and_duration_match_ros2_bag_info(), test_expected_topics_missing_from_the_recording_are_listed_not_invented(), test_the_run_identity_beside_the_bag_is_embedded(), test_the_summary_is_deterministic_byte_for_byte() (+1 more)

### Community 141 - "hub_motor_wheel"
Cohesion: 0.12
Nodes (17): hub_motor_wheel, bom, bom_row, brake_side, class, dimension_source, envelope, links (+9 more)

### Community 142 - "evaluations/service.py"
Cohesion: 0.09
Nodes (21): utcnow(), claim(), finish(), heartbeat(), input_sha256(), lease_delta(), load_input(), persist_success() (+13 more)

### Community 143 - "Bundled third-party assets"
Cohesion: 0.12
Nodes (14): Earlier distributions, OpenAMRobot licensing standard, Ownership and branding, Third-party material, AprilTag panel texture, Botshare LTD and project ownership, Bundled third-party assets, CAN software-in-the-loop emulators from openamr-platform-fw (+6 more)

### Community 144 - "castor"
Cohesion: 0.12
Nodes (16): bom, bom_row, class, dimension_source, envelope, file, links, name (+8 more)

### Community 145 - "nodes"
Cohesion: 0.12
Nodes (16): glb, bytes, file, node_count, nodes, primitives, sha256, triangles (+8 more)

### Community 146 - "trial-exercise.spec.ts"
Cohesion: 0.14
Nodes (7): evaluate(), EXPECTED, pick(), ROOT, run, t, timings

### Community 147 - "generated_by"
Cohesion: 0.13
Nodes (15): generated_by, cadlib_sha256, command, converter_sha256, map, tool, versions, file (+7 more)

### Community 148 - "assistant.py"
Cohesion: 0.21
Nodes (6): call(), list_tools(), _loopback(), ToolCallIn, ToolCallOut, ToolDescriptor

### Community 149 - "Simulation execution and Experiment Studio"
Cohesion: 0.13
Nodes (14): Architecture note, Camera-configuration comparisons: infrastructure check, Execution, Experiment specification (`pap.experiment-spec/1`), immutable, First scenario: OpenAMRobot command-loss stop (#79 / PR #177), Layers, Not built yet, Preparation for camera-configuration comparisons (+6 more)

### Community 150 - "model.py"
Cohesion: 0.23
Nodes (4): _clock_summary(), _sha256(), _storage_id(), summarize_bag()

### Community 151 - "catalog.py"
Cohesion: 0.16
Nodes (7): ArtifactDef, Catalog, CatalogError, load_catalog(), Output, Simulator, _now()

### Community 153 - "source"
Cohesion: 0.15
Nodes (12): files, name, omitted, slug, source, commit, license_spdx, note (+4 more)

### Community 154 - "TopicTracker"
Cohesion: 0.36
Nodes (5): TopicTracker, test_a_latched_topic_is_never_stale_after_its_one_message(), test_a_topic_nobody_publishes_is_not_called_fresh_or_never(), test_heavy_topics_are_reported_as_not_sampled(), test_silence_right_after_subscribing_is_pending_then_never()

### Community 155 - "Architecture"
Cohesion: 0.17
Nodes (11): auth(), Architecture, Components, Decisions, Evaluation pipeline (one job), Identity and authorization, Jobs, Outcome classes per episode (a labelled cross-tabulation, not a statistic) (+3 more)

### Community 156 - "Observation.tsx"
Cohesion: 0.29
Nodes (11): cell(), isRecordArray(), NestedHint(), num(), ObsState(), PROBLEM, RecordTable(), STATE_KEYS (+3 more)

### Community 157 - "Open-source integration registry"
Cohesion: 0.11
Nodes (15): G-2 Building `outcome.verified.conditions` from a verifier report is importer-internal, Community 189 - "conditions_of", Adopted now (minimum set for the first Release Intelligence workflow), Benchmarks (reproducible workloads), Considered and deferred, Dev-only (never shipped), External robotics systems and agent runtimes (evidence sources only), Industrial and scientific integrations (future evidence sources) (+7 more)

### Community 158 - "Real robot evidence: CoreSense drone flights (Milestone B)"
Cohesion: 0.18
Nodes (9): Accounting, Claims this evidence cannot support, Integration effort, Provenance, Real robot evidence: CoreSense drone flights (Milestone B), Reproduce, Result, Verification rule applied (+1 more)

### Community 159 - "inputs"
Cohesion: 0.18
Nodes (11): inputs, checkout_commit, git_ref, last_commit_for_file, member, member_sha256, name, note (+3 more)

### Community 160 - "oidc-provider.mjs"
Cohesion: 0.20
Nodes (7): jwk, provider, server, { values: a }, oidc-provider@9.13.3, RFC-8707, oidc-provider

### Community 161 - "Any"
Cohesion: 0.22
Nodes (4): summarize(), TfTracker, test_summary_counts_required_problems_only(), test_tf_static_frames_report_no_age_and_roots_are_listed()

### Community 162 - "test_model.py"
Cohesion: 0.25
Nodes (7): is_hidden(), fed(), test_a_fast_topic_goes_stale_after_two_seconds_of_silence(), test_a_slow_topic_is_not_called_stale_before_five_of_its_own_periods(), test_a_transient_local_topic_that_keeps_publishing_is_judged_by_freshness(), test_expected_topics_are_missing_stale_or_present(), test_hidden_names_follow_the_ros_convention()

### Community 163 - "make_handler"
Cohesion: 0.28
Nodes (5): clean(), make_handler(), do_GET(), _refuse(), _send()

### Community 164 - "prometheus"
Cohesion: 0.22
Nodes (9): cap_drop, command, image, ports, profiles, restart, security_opt, volumes (+1 more)

### Community 165 - "OpenMHS interface gaps"
Cohesion: 0.22
Nodes (8): G-3 No engine-native per-arm unknown-reason breakdown, G-4 No statement of minimum detectable effect, G-5 Timeouts and cancellation are process-level only, G-6 Correlated attempts beyond scenario ids, G-7 Only pass/fail rates are compared, never the measured values themselves, G-8 "No change" cannot be established with a near-perfect baseline, G-9 A comparison cannot tell the platform which arm lacks a stratum, OpenMHS interface gaps

### Community 166 - "base_camera"
Cohesion: 0.22
Nodes (9): bytes, file, frame, material, rgba, sha256, triangles, triangles_before_decimation (+1 more)

### Community 167 - "base_chassis"
Cohesion: 0.22
Nodes (9): bytes, file, frame, material, rgba, sha256, triangles, triangles_before_decimation (+1 more)

### Community 168 - "base_covers"
Cohesion: 0.22
Nodes (9): bytes, file, frame, material, rgba, sha256, triangles, triangles_before_decimation (+1 more)

### Community 169 - "base_equipment"
Cohesion: 0.22
Nodes (9): bytes, file, frame, material, rgba, sha256, triangles, triangles_before_decimation (+1 more)

### Community 170 - "caster"
Cohesion: 0.22
Nodes (9): bytes, file, frame, material, rgba, sha256, triangles, triangles_before_decimation (+1 more)

### Community 171 - "motor_driver"
Cohesion: 0.22
Nodes (9): components, motor_driver, bom, bom_row, envelope, name, output, qty (+1 more)

### Community 172 - "hub_motor_wheel"
Cohesion: 0.22
Nodes (9): bytes, file, frame, material, rgba, sha256, triangles, triangles_before_decimation (+1 more)

### Community 173 - "imu"
Cohesion: 0.22
Nodes (9): bytes, file, frame, material, rgba, sha256, triangles, triangles_before_decimation (+1 more)

### Community 174 - "lidar"
Cohesion: 0.22
Nodes (9): bytes, file, frame, material, rgba, sha256, triangles, triangles_before_decimation (+1 more)

### Community 175 - "tof"
Cohesion: 0.22
Nodes (9): tof, bytes, file, frame, material, rgba, sha256, triangles (+1 more)

### Community 176 - "ultrasonic"
Cohesion: 0.22
Nodes (9): ultrasonic, bytes, file, frame, material, rgba, sha256, triangles (+1 more)

### Community 177 - "Handoff to Codex: Physical AI Platform (2026-11-23)"
Cohesion: 0.29
Nodes (6): Handoff to Codex: Physical AI Platform (2026-11-23), Open work, in order, Pitfalls on this machine, Rules you must keep, State, Using the code graph

### Community 178 - "scrape_configs"
Cohesion: 0.22
Nodes (8): global, evaluation_interval, scrape_interval, scrape_configs, job_name, metrics_path, static_configs, targets

### Community 179 - "healthcheck"
Cohesion: 0.57
Nodes (8): healthcheck, interval, retries, test, timeout, healthcheck, healthcheck, healthcheck

### Community 180 - "virtual-lab"
Cohesion: 0.25
Nodes (8): virtual-lab, cap_drop, image, ports, read_only, restart, security_opt, tmpfs

### Community 181 - "x-api-env"
Cohesion: 0.25
Nodes (8): x-api-env, OTEL_EXPORTER_OTLP_ENDPOINT, PAP_AUTH_MODE, PAP_DATABASE_URL, PAP_ENV, PAP_ENVIRONMENTS, PAP_MAX_UPLOAD_BYTES, PAP_METRICS_TOKEN

### Community 182 - "Agentic harness (HAR-001)"
Cohesion: 0.25
Nodes (7): Agentic harness (HAR-001), Not built yet, Orchestration, Run it, Spend and secrets, What it can and cannot do, What the tests do and do not show

### Community 183 - "base_link_frame"
Cohesion: 0.25
Nodes (8): base_link_frame, axle_height_above_castor_floor_mm, castor_contact_spread_mm, design_base_link_height_mm, offset_mm, release001_axle_midpoint_step_mm, release001_track_mm, release001_wheel_radius_mm

### Community 184 - "test_storage_s3.py"
Cohesion: 0.17
Nodes (9): bucket(), chunks(), make_client(), s3_endpoint(), storage(), test_full_evaluation_with_s3_storage(), test_one_interface_two_adapters(), test_s3_too_large_upload_leaves_nothing() (+1 more)

### Community 185 - "explain_event"
Cohesion: 0.39
Nodes (3): explain_event(), _judged(), _short()

### Community 186 - "JointTracker"
Cohesion: 0.43
Nodes (4): finite(), JointTracker, test_a_frozen_joint_keeps_its_fresh_stamp_but_reports_how_long_it_has_not_moved(), test_non_finite_sensor_values_become_no_value_not_invalid_json()

### Community 187 - "start.sh"
Cohesion: 0.29
Nodes (7): dc(), PAP_API_PORT, PAP_AUTH_MODE, PAP_ENV, PAP_LAB_PORT, PAP_WEB_PORT, start.sh script

### Community 188 - "test_scaffold.py"
Cohesion: 0.19
Nodes (6): get_engine(), test_health_is_degraded_when_the_engine_digest_is_wrong(), test_health_reports_database_and_engine(), test_oidc_mode_needs_issuer_and_audience(), test_production_refuses_dev_auth(), test_sqlite_is_refused()

### Community 189 - "run_session"
Cohesion: 0.27
Nodes (4): _finish(), run_session(), Session, Budget

### Community 190 - "step_check"
Cohesion: 0.48
Nodes (7): step_check, step_check, component, kind, map, max_delta_mm, step

### Community 191 - "ros_stack.sh"
Cohesion: 0.33
Nodes (6): inside(), MSYS_NO_PATHCONV, PAP_ROS_DOMAIN, PAP_ROS_OBSERVER_PORT, ros_stack.sh script, WSLENV

### Community 195 - "ros_stack_wsl.sh"
Cohesion: 0.40
Nodes (5): PYTHONDONTWRITEBYTECODE, PYTHONPATH, ROS_DOMAIN_ID, ros_stack_wsl.sh script, stop_all()

### Community 196 - "Design audit, 2026-11-21 (Impeccable `audit`, web)"
Cohesion: 0.40
Nodes (4): Audit health score, Design audit, 2026-11-21 (Impeccable `audit`, web), Findings, Positive findings

### Community 197 - "budgets"
Cohesion: 0.40
Nodes (5): glb_max_bytes, glb_target_bytes, stl_max_bytes, stl_total_max_bytes, budgets

### Community 199 - "eslint.config.mjs"
Cohesion: 0.40
Nodes (4): compat, config, @eslint/eslintrc@3.3.7, @eslint/eslintrc

### Community 201 - "run_scenario.sh"
Cohesion: 0.50
Nodes (3): GZ_PARTITION, ROS_DOMAIN_ID, run_scenario.sh script

### Community 202 - "compose"
Cohesion: 0.50
Nodes (4): name, runs-on, timeout-minutes, compose

### Community 203 - "trial"
Cohesion: 0.50
Nodes (4): trial, name, runs-on, timeout-minutes

### Community 208 - "test_ros_workspace.py"
Cohesion: 0.32
Nodes (7): ros(), snap(), test_a_replay_says_it_is_a_replay(), test_discovery_through_the_unchanged_adapter_finds_readable_properties_and_no_actions(), test_live_reads_pass_through_what_the_observer_reports_without_filling_anything_in(), test_no_workflow_can_be_defined_against_an_observer_device(), test_the_executors_safety_check_would_refuse_an_observer_device_anyway()

### Community 219 - "time"
Cohesion: 0.22
Nodes (3): sim_now(), travel(), wait_sim()

### Community 220 - "csv"
Cohesion: 0.33
Nodes (5): main(), render(), rows(), ts(), coresense()

### Community 221 - "Graph Report - physical-ai-platform  (2026-11-23)"
Cohesion: 0.20
Nodes (9): Community Hubs (Navigation), Corpus Check, Graph Freshness, Graph Report - physical-ai-platform  (2026-11-23), Import Cycles, Knowledge Gaps, Suggested Questions, Summary (+1 more)

### Community 222 - "Prompt for Codex (paste this as the first message)"
Cohesion: 0.25
Nodes (7): 1. Read, in this order (do not skip, do not re-explore the repo afterwards), 2. What the product is, 3. Non-negotiable rules, 4. How to work (the harness loop), 5. Open work, in priority order, 6. Definition of done for anything you finish, Prompt for Codex (paste this as the first message)

### Community 223 - "Session handoff (2026-11-23)"
Cohesion: 0.25
Nodes (7): Known limits to state, never hide, Pitfalls learned this session, Secrets, Session handoff (2026-11-23), What is left, in order, What was built and verified this session (evidence is in `harness/features.json`), Where the repository stands

### Community 224 - "extract.py"
Cohesion: 0.48
Nodes (3): main(), rows_for(), sha256()

### Community 225 - "Prompt for the next Claude session (paste as the first message)"
Cohesion: 0.29
Nodes (6): Non-negotiable rules, Prompt for the next Claude session (paste as the first message), Read first, in this order, and then do not re-explore the repository, State in one paragraph, Working style (keeps quota low), Your tasks, in order (stop and report after each numbered group)

### Community 226 - "pg.py"
Cohesion: 0.38
Nodes (3): fresh_database(), _libpq(), test_upgrade_downgrade_upgrade_on_empty_database()

### Community 227 - "test_trial_baseline.py"
Cohesion: 0.43
Nodes (3): engine_output(), test_baseline_matches_engine(), test_baseline_mcnemar_matches_engine()

### Community 230 - "env.py"
Cohesion: 0.60
Nodes (3): run_offline(), run_online(), url()

## Knowledge Gaps
- **29 isolated node(s):** `RFC-8707`, `RFC-0004`, `RFC-0005`, `RFC-3339`, `PAP_IDENTITY_NOTE` (+24 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 1750 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **44 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `God Nodes (most connected - your core abstractions)` connect `fixture` to `deps.py`, `test_auth.py`, `get_settings`, `api`, `as_user`, `Graph Report - physical-ai-platform  (2026-11-23)`?**
  _High betweenness centrality (0.210) - this node is a cross-community bridge._
- **What connects `RFC-8707`, `RFC-0004`, `RFC-0005` to the rest of the system?**
  _29 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `[project]/page.tsx` be split into smaller, more focused modules?**
  _Cohesion score 0.053562653562653564 - nodes in this community are weakly interconnected._
- **Why does `api()` connect `api` to `[project]/page.tsx`, `experiments.ts`, `Twin.tsx`, `fixture`, `Onboarding a team`, `AppShell.tsx`, `Graph Report - physical-ai-platform  (2026-11-23)`?**
  _High betweenness centrality (0.149) - this node is a cross-community bridge._
- **Should `test_pipeline_real.py` be split into smaller, more focused modules?**
  _Cohesion score 0.13548387096774195 - nodes in this community are weakly interconnected._
- **Why does `Notice()` connect `api` to `[project]/page.tsx`, `experiments.ts`, `Twin.tsx`, `fixture`, `AppShell.tsx`?**
  _High betweenness centrality (0.089) - this node is a cross-community bridge._
- **Should `evaluations/routes.py` be split into smaller, more focused modules?**
  _Cohesion score 0.08121158911325724 - nodes in this community are weakly interconnected._
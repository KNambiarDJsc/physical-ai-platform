# Rules for any coding agent working in this repository

These apply to every agent (and every human) regardless of tool. CLAUDE.md adds session mechanics.

## Scope

- Work on one feature from `harness/features.json` at a time. Do not start a feature whose dependencies are
  not `verified`. Do not start Phase 6 modules (fleet, incidents beyond what releases need, CI integrations,
  HIL) before E2E-001 is verified.
- Make the smallest coherent vertical slice that satisfies the acceptance criteria. No speculative
  abstractions, no empty directories to match a diagram.

## Boundaries

- OpenMHS is a dependency, not part of this repo. Read it, build it from the pinned commit, never edit it.
  Interface needs go to `docs/engine-contract-gaps.md`.
- OpenAMRobot AI Studio is a separate project. Patterns may be reused (same owner); robotics control code
  may not. Nothing here touches upstream OpenAMRobot contributions.
- No dependency is added unless an acceptance criterion needs it. Each new one gets a row in
  `docs/open-source-integration-registry.md` (license, version, decision) before it is used.
- No Kafka, Kubernetes, Redis, vector databases, LLM frameworks or microservices without a recorded
  decision showing the requirement.

## Evidence

- A feature is `verified` only with recorded passing commands for every criterion.
- Never weaken, skip or delete a test to make a gate pass. Never edit expected outputs to match a bug.
- A mocked engine response is fine for a unit test of parsing or error handling; it never proves an
  end-to-end criterion.
- If the same operation fails twice, stop and diagnose before trying again. Record unresolved failures in
  `harness/blockers.md`.

## Safety

- Commands go only to environments the operator configured `simulated` whose devices also report
  `simulated=true` (D-026). Physical environments are discovered and read, never commanded. The platform is never in
  a robot's real-time or safety path. An experiment approval applies to one exact checksum (D-037); simulation hosts
  refuse rather than degrade (D-038); the agent harness can request, never approve (D-039).
- Uploaded files and engine inputs are untrusted: size-limit, parse defensively, never pass them through a
  shell, never use a client filename as a path.
- No credentials in code, fixtures, docs or logs. Configuration comes from the environment.
- No claims of safety certification, regulatory compliance, hardware validation or customer results that
  have not happened.

## Hand-off

Every session ends with `harness/progress.md` stating: what changed, the evidence, what is next, and what
is uncommitted. The next agent should not need the conversation.

## Handoff (start here if you are new, including Codex)

- `docs/HANDOFF.md`: what exists, where, the invariants, how to run, test and extend.
- `docs/handoff/SESSION_HANDOFF.md`: the exact current state, what is left, known limits, pitfalls; prompts for the next
  session are `NEXT_CLAUDE_PROMPT.md` and `CODEX_PROMPT.md` beside it.
- `docs/handoff/CODEX_HANDOFF.md`: the earlier briefing (state, open work, pitfalls).
- `docs/handoff/graphify/`: a code graph of this repository (GRAPH_REPORT.md for people, graph.json for tools).
  Query it with `graphify query "<question>"`, `graphify explain "<symbol>"`, `graphify path "A" "B"`,
  `graphify affected "<symbol>"`; refresh with `graphify update .` (AST only, no API key, nothing leaves the machine).
  The graph is a map: read the source before relying on an answer.
- `harness/features.json` (every feature, its acceptance criteria and evidence), `harness/decisions.md` (D-001..),
  `harness/progress.md` (session log), `harness/blockers.md`.


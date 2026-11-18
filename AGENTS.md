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

- This platform observes. It never issues motion commands, never writes to industrial equipment, and is
  never in a robot's real-time or safety path.
- Uploaded files and engine inputs are untrusted: size-limit, parse defensively, never pass them through a
  shell, never use a client filename as a path.
- No credentials in code, fixtures, docs or logs. Configuration comes from the environment.
- No claims of safety certification, regulatory compliance, hardware validation or customer results that
  have not happened.

## Hand-off

Every session ends with `harness/progress.md` stating: what changed, the evidence, what is next, and what
is uncommitted. The next agent should not need the conversation.

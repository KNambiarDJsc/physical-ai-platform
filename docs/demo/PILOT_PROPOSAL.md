# Technical pilot proposal: evidence-based validation of laboratory procedures

**For:** Richard Rösch, Fraunhofer IPA / nICLAS. **Status:** a proposal for discussion; scope, duration and terms are to
be agreed. Nothing below has been validated on physical laboratory hardware.

## Why

Autonomous laboratories need a way to show that a procedure, or a change to one, does what it claims, with evidence a
second person can inspect. The platform makes that a routine: a researcher states a procedure and an explicit tolerance,
a different person approves exactly what runs, a worker executes it on a simulated bench, and an independent engine
judges the instrument's own report against what was measured. An agent can investigate a failure from the stored
evidence and draft a follow-up; it cannot approve or run anything.

## What the pilot would do

| Phase (proposed) | Work | Outcome |
|---|---|---|
| 1. Setup (about 2 weeks) | Install self-hosted on a Fraunhofer machine. Describe 2 to 3 of your instruments, or their simulators, as W3C WoT Thing Descriptions (LabThings or HTTP); discover them in the Hardware Hub. | Devices and capabilities visible, labelled simulated. |
| 2. Procedures (about 3 weeks) | Express 3 to 5 of your protocols as workflows with verification contracts (the measurement that independently checks the claim, and its tolerance). Include one realistic fault per protocol, injected in simulation. | Each protocol has a passing and a failing, reproducible run, judged by the engine. |
| 3. Agent-assisted investigation (about 2 weeks) | Use the agent on the failing runs with your model endpoint and a stated budget. Measure how often its findings are grounded in stored evidence. | A written assessment of where it helps and where it does not. |
| 4. Review (about 1 week) | Joint review of evidence reports, gaps and next steps. | Go / no-go for a physical-instrument phase, with its safety review. |

## What we need from you

One or two researchers for a few hours a week; instrument descriptions or simulators; a named contact for safety and
IT questions; a machine (see the requirements sheet) and, for phase 3, an OpenAI-compatible model endpoint with an agreed
spend cap.

## Success criteria (measurable)

- At least three of your instruments discovered and described with accurate capabilities.
- At least three protocols with a passing run and a reproducible failing run, each judged by the pinned engine.
- Every report regenerates byte for byte from stored records.
- No command ever reaches a device that is not simulated; every run was approved by someone other than its requester.
- Phase 3: each agent finding cites ids that exist in the tool results, and the assessment states its failure modes.

## Boundaries, stated plainly

Simulation first. The pilot does not command physical hardware, does not claim safety certification or regulatory
compliance, and does not use customer data. Moving to physical instruments would be a separate decision after a safety
review. Today the pump and balance are a simulated bench with a seeded noise model, so agreement with a real instrument's
behaviour is not claimed.

## Data and control

Self-hosted: evidence stays on your machine. The model key is held only in the server's environment. Workspaces are
isolated from each other. The engine build is pinned by commit and digest, so a result names the exact verifier.

## Open points for discussion

Which protocols matter most; which instruments can be described; how a fault should be modelled for each; what an
acceptable tolerance and failure rate look like; commercial terms, ownership of adapters and publication.

# Agentic harness (HAR-001)

`packages/agent-harness` runs a [Strands](https://strandsagents.com) agent over the platform's own agent tools. It is a
separate uv project (Strands brings its own dependency set) and is checked by `scripts/verify.sh`.

## What it can and cannot do

- It works only through `pap_agent_tools` (the allowlist the MCP server and the in-app assistant also use), and every
  call runs **as the person who started it**, so the platform's roles and workspace isolation apply.
- Read-only by default: experiments and their runs, trials, verdicts, recordings and event explanations, workflow runs,
  evaluations and release verdicts, devices and observations.
- With `--allow-requests` it may also *record* a request to run one exact experiment version, or a proposal to run an
  existing workflow. An engineer other than the requester still approves; nothing runs otherwise.
- There is no tool to approve, start a run, create or edit an experiment or workflow, or command a device.
- Its instructions require it to cite the ids it relies on, say what is not known, label simulated evidence, and never
  call a violated trial a release regression (only the engine's release comparison can say that).

## Spend and secrets

- The model is any OpenAI-compatible endpoint: `PAP_LLM_API_KEY`, `PAP_LLM_BASE_URL`, `PAP_LLM_MODEL` as **environment
  variables**. The key is never written to a file, a log or a trace.
- A hard cap per session: tokens always (`PAP_LLM_MAX_TOKENS`, default 200 000), and dollars when prices are set
  (`PAP_LLM_USD_PER_M_INPUT`, `PAP_LLM_USD_PER_M_OUTPUT`; cap `--max-usd` or `PAP_LLM_MAX_USD`, default 0.50). The session
  stops before the model call that would go over, and the trace says so.

## Run it

```bash
cd packages/agent-harness
uv run pap-harness ask --org demo --as ada "Why did the pre-fix arm of the command-loss experiment fail?"
uv run pap-harness ask --org demo --as ada --allow-requests --max-usd 0.20 "Is there enough evidence to call it a regression?"
```

Each session writes `var/agent-traces/<id>.json` (`pap.agent-trace/1`): the question, the model, every model call with
its tokens, every tool call with its input, whether it was permitted, a digest of its output and any error, the answer,
why it stopped, and the usage.

## Not built yet

Traces stored in and shown by the platform (the Agents page), multi-step plans that wait for an approval and continue,
and evaluation of the agent's answers against known cases.

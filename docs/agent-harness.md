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

## Orchestration

- **Providers** are configuration: `PAP_LLM_PROVIDER` = `openai` (any OpenAI-compatible endpoint, the default),
  `anthropic`, `bedrock`, `ollama` or `litellm` (install that provider's Strands extra).
- **Fast paths**: "status of run <id>", "list experiments", "verdicts for <experiment>" are answered by fixed tool calls
  and a template, with no model call and no cost. `--no-fast-paths` sends everything to the model.
- **Discovery** is scoped to the caller: a non-member gets no tools; writes are offered only with `--allow-requests`.
- **Parallel reads**: independent read tools in one turn run concurrently; writes run one at a time.
- **Recovery**: a read that fails transiently (no answer, HTTP 5xx) is retried twice with backoff; any tool error is
  returned to the model as text, never ends the session.
- **Bounds**: a step limit (`--max-steps`, model calls), a timeout (`--timeout-s`), Ctrl-C cancels cleanly; each stops
  before the next model call and is written to the trace.
- **Approval**: each write asks the person running the session to confirm before it is sent (refused when there is no
  terminal); an engineer then decides on the platform.
- **Grounding**: after an answer, every id it cites is checked against the tool outputs of the session; unsupported ids,
  or an answer without citations after tool use, are reported.
- **Sessions** persist under `var/agent/sessions` (Strands file sessions) and resume with `--session <id>`.

## Spend and secrets

- The model is any OpenAI-compatible endpoint: `PAP_LLM_API_KEY`, `PAP_LLM_BASE_URL`, `PAP_LLM_MODEL` as **environment
  variables**. The key is never written to a file, a log or a trace.
- A per-experiment budget (`--experiment <slug> --experiment-max-usd/--experiment-max-tokens`) is kept in
  `var/agent/ledger.json` across sessions; a session is refused before it starts once it is spent.
- A hard cap per session: tokens always (`PAP_LLM_MAX_TOKENS`, default 200 000), and dollars when prices are set
  (`PAP_LLM_USD_PER_M_INPUT`, `PAP_LLM_USD_PER_M_OUTPUT`; cap `--max-usd` or `PAP_LLM_MAX_USD`, default 0.50). The session
  stops before the model call that would go over, and the trace says so.

## Run it

```bash
cd packages/agent-harness
uv run pap-harness ask --org demo --as ada "Why did the pre-fix arm of the command-loss experiment fail?"
uv run pap-harness ask --org demo --as ada --allow-requests --max-usd 0.20 "Is there enough evidence to call it a regression?"
```

Each session writes `var/agent/traces/<id>.json` (`pap.agent-trace/1`): the question, the model, every model call with
its tokens, every tool call with its input, whether it was permitted, a digest of its output and any error, the answer,
why it stopped, and the usage.

## What the tests do and do not show

The tests run the orchestration with a scripted stand-in model. They show the guarantees above hold; they say nothing
about how well a real model investigates. That is measured only with a real model run, recorded with its trace.

## In the website (the Agent page)

`/agent` runs a session as the signed-in person and shows the answer, its cost and its full trace (`app/agent/sessions.py`,
D-040). The API starts `pap-harness ask` as a subprocess with the caller's own credential, so the platform's roles and
workspace isolation apply to everything the agent reads, and the harness's environment holds only the model settings and
that credential. Asking needs the engineer role; viewers can read what engineers asked. Limits (all server settings):
`PAP_AGENT_SESSION_USD` per session, `PAP_AGENT_DAILY_USD` and `PAP_AGENT_DAILY_SESSIONS` per day over the server,
`PAP_AGENT_MAX_RUNNING` at once, `PAP_AGENT_TIMEOUT_S`, `PAP_AGENT_MAX_STEPS`. The runner is `uv run --project
packages/agent-harness pap-harness` unless `PAP_AGENT_COMMAND` says otherwise (a JSON list or a command line).

- **No model configured:** the page says so and still answers the fixed questions, including `Investigate workflow run
  <id>.`: the platform's rule-based investigation of a laboratory run. It is labelled "no model used" and cites the ids
  it read. It is the scripted fallback and is not AI inference.
- **Drafting:** an engineer may tick "let the agent draft a follow-up". The agent can then call `propose_experiment` or
  `request_experiment_run`; the call is recorded as a *draft* in the trace and sent nowhere. The page shows it, and a
  person files it with a click, as themselves; a different person must still approve it. The website never passes
  `--allow-requests`.
- **Simulated evidence:** when the tool results say the evidence is simulated and the model's answer does not, the
  harness appends a note marked as the platform's own words.
- **Speed:** `PAP_LLM_REASONING_EFFORT=low` (OpenAI-compatible reasoning models) cut one small request from 18 s to 7.5 s
  in a single measurement; it is a speed setting, and the harness checks answers either way.
- **Key:** `PAP_LLM_*` in the server's environment only; the page never sees it and a failed session's message is scrubbed.

## Not built yet

Multi-step plans that wait for an approval and continue, evaluation of the agent's answers against known cases, and an
approver's view of an agent's draft inside the Workflows page (today the person who files it follows a link).

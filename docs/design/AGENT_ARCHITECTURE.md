# Engineering Agent architecture

| Capability | Implementation boundary |
|---|---|
| Ask about a selection | The inspector passes the recorded ID into an editable question. The engineer submits it to the workspace session API. |
| Gather observations | The harness uses the typed registry with caller credentials. Server authorization applies on each API operation. |
| Explain a recording event | The deterministic assistant identifies its rule and evidence. The Engineering Agent separately exposes its session and trace. |
| Draft and file | The session view renders a structured draft when returned. Filing is a human action. |
| Approve and execute | The experiment service checks the reviewer and version checksum. The durable worker dispatches approved simulated operations. |

The model provider belongs in server configuration. Keep model costs and traces on their session. A recording ID identifies an artifact. It cannot authorize execution. Agent prompts should name the domain, selected entity, observation and uncertainty while using the same runtime. The existing session and execution state machines own different transitions. Future resume-after-approval needs a persisted link between them.

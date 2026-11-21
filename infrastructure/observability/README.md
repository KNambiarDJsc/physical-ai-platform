# Observability (optional)

`docker compose --profile observability up -d` adds an OpenTelemetry Collector and Prometheus next to the product, and
`OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318` makes the API and the worker send traces to it.

| Service | What it does | Image (pinned by version and digest) |
|---|---|---|
| `otel-collector` | receives OTLP/HTTP traces, prints them (debug exporter) | `otel/opentelemetry-collector:0.164.0` |
| `prometheus` | scrapes `api:8000/metrics` and `worker:9100/metrics` every 5 s, UI on `127.0.0.1:9090` | `prom/prometheus:v3.15.1` |

Both are unmodified upstream images (Apache-2.0). Grafana, Loki and Tempo are AGPL-3.0: if you want them, run them as
separate, unmodified services of your own; they are never bundled into a product image of ours.

What is emitted: spans named `engine <command>` for every OpenMHS engine call, request spans from the API, and metrics
`pap_http_request_duration_seconds`, `pap_job_duration_seconds`, `pap_engine_invocations_total` and others.

Checked by `bash scripts/smoke.sh --compose --observability` (needs Docker): after a real evaluation, the collector's log
contains `engine ...` spans and Prometheus reports both scrape targets up with engine invocations counted.

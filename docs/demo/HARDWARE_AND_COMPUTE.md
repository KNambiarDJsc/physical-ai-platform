# Hardware and computing requirements

What the pilot needs, separating what was **measured** on the development machine from what is **an estimate**. No
physical laboratory hardware is needed for the pilot's first phases: the instruments are simulated.

## Measured on the demonstration machine

| | |
|---|---|
| Machine | Windows 11, Intel Core i7-10700 (8 cores, 16 threads), 15.8 GB RAM, SSD |
| Whole stack idle after start-up | about 0.8 GB resident across about 66 processes: PostgreSQL, API, worker, web server, virtual laboratory, two simulation hosts, ROS 2 replay (measured) |
| During a full journey (two runs, one agent session, browser open) | about 0.9 GB for the stack; the browser is extra (measured) |
| Building the web app | needs a 2 GB JavaScript heap (`NODE_OPTIONS=--max-old-space-size=2048`); about 2 to 4 minutes (measured) |
| A simulated dispense run | about 1 second of worker time (measured) |
| A real Gazebo run (optional, not used in the 10-minute journey) | the host refuses to start unless 1.5 GB is free inside WSL, 1 GB free on Windows and 1 GB of disk are available; about 2 minutes per run, one at a time (from `docs/simulation-studio.md`) |
| Full automated gate | `verify.sh` about 10 minutes, browser suite about 5 minutes, on this machine (measured) |

The development machine often had only 1 to 3 GB free while other programs ran. That is enough for the stack but not for
a build plus a Gazebo run at the same time.

## Recommended for a pilot installation (estimate, not benchmarked)

| Item | Suggested |
|---|---|
| Server | 4 vCPU, 8 GB RAM, 50 GB disk for the platform, PostgreSQL and evidence storage |
| Optional simulation | add 4 GB RAM and 20 GB disk per simulator that runs alongside (Gazebo needs the 1.5 GB above and a ROS 2 workspace) |
| Operating system | Linux or Windows with Docker (the Compose stack is built and exercised in CI) or the no-Docker developer stack |
| Storage | local volume, or any S3-compatible store (MinIO, SeaweedFS, Ceph, R2) |
| Browsers | the interface is tested in Chromium and checked against WCAG 2.1 AA with axe; other browsers are not tested |
| Network | ports 3000 (web) and 8000 (API) inside your network; no inbound internet access is needed |

## Agent and model

The agent needs an OpenAI-compatible model endpoint of your choice (a hosted API, or a local server such as vLLM or
Ollama). Measured through a hosted OpenAI-compatible endpoint:

- `anthropic/claude-haiku-4.5` (the demo model): one investigation is 3 model calls, about 22,000 tokens in and 1,300
  out, about **$0.03**, about **15 seconds**;
- `openai/gpt-oss-120b`: about 6,700 in and 1,000 out, about $0.0004, but 12 to 111 seconds depending on the provider's
  load, and on one day the provider returned 502 for every request with tool definitions on that model;
- the platform caps spend per session ($0.25 by default), per day ($1.00) and sessions at once (2); all are settings.

Nothing leaves your installation except what your own model endpoint receives in a session: the tool results the asker could
already read. With no model, the fixed questions and the rule-based investigation still work.

## Physical hardware

None is connected and none is required for phases 1 to 3 of the proposal. A real instrument would need a description as a
W3C WoT Thing (LabThings or a plain HTTP interface) and an operator-configured environment; physical environments are
read-only until a separate safety review says otherwise. The platform is never placed in an instrument's real-time or
safety path, and nothing in this sheet is a safety claim.

## Not measured

Throughput under concurrent users, long-running load, very large evidence sets (uploads are limited to 100 MiB by
default, captures to 96 MiB), and behaviour on other operating systems or on an ARM server.

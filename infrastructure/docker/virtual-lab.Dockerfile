# syntax=docker/dockerfile:1.7
# The virtual laboratory: simulated instruments served by labthings-fastapi (runtimes/virtual-lab, its own lock).
# Simulation only; no hardware access. Build context: the repository root.
#   docker build -f infrastructure/docker/virtual-lab.Dockerfile -t pap-virtual-lab:local .

ARG PYTHON_IMAGE=python:3.12.16-slim-bookworm@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.7.11@sha256:d7e699d374d4e5cb52a37d5c8f0ee15e3c7572850325953bf9fa8d781cfa92fc

FROM ${UV_IMAGE} AS uv
FROM ${PYTHON_IMAGE} AS deps
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /app
COPY runtimes/virtual-lab/pyproject.toml runtimes/virtual-lab/uv.lock ./
COPY runtimes/virtual-lab/src src
RUN uv sync --frozen --no-dev

FROM ${PYTHON_IMAGE} AS runtime
RUN groupadd --system --gid 10002 vlab \
 && useradd --system --uid 10002 --gid vlab --home-dir /nonexistent --no-create-home --shell /usr/sbin/nologin vlab
COPY --from=deps /app /app
ENV PATH=/app/.venv/bin:$PATH PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PAP_VLAB_SETTINGS=/tmp/vlab-settings
USER vlab
WORKDIR /tmp
EXPOSE 8100
CMD ["python", "-m", "pap_virtual_lab.server", "--host", "0.0.0.0", "--port", "8100"]

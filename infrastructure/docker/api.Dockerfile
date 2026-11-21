# syntax=docker/dockerfile:1.7
# API and evaluation worker image (one image, two commands).
#
# The OpenMHS engine is built here from engine.lock.json (repository + commit), never copied from a developer
# machine. Its digest is recorded in /app/.engine/build.json, which the bridge reads and checks before every run.
# Rust release builds are not bit-reproducible across machines, so the digest is the one this build produced;
# the commit is what pins the engine's behaviour (D-002).
#
# Build context: the repository root.
#   docker build -f infrastructure/docker/api.Dockerfile -t pap-api:local .

ARG RUST_IMAGE=rust:1.89.0-slim-bookworm@sha256:d7fc7de78bb8c1469933aeecbf801314d30d7d6e9f0578bba4cfa285bfa37fe6
# Runtime base: newest official rebuild (D-023): 3.12.11 carried 46 fixable HIGH/CRITICAL OS findings, 3.12.16 has 0.
ARG PYTHON_IMAGE=python:3.12.16-slim-bookworm@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.7.11@sha256:d7e699d374d4e5cb52a37d5c8f0ee15e3c7572850325953bf9fa8d781cfa92fc

# --- engine: the pinned OpenMHS commit, built with its own Cargo.lock ------------------------------------------
FROM ${RUST_IMAGE} AS engine
RUN apt-get update \
 && apt-get install -y --no-install-recommends git ca-certificates jq \
 && rm -rf /var/lib/apt/lists/*
COPY engine.lock.json /lock/engine.lock.json
WORKDIR /src
# CARGO_BUILD_JOBS keeps memory bounded on small builders; raise it on CI with --build-arg.
ARG CARGO_BUILD_JOBS=2
RUN set -eu; \
    repo="$(jq -er .repository /lock/engine.lock.json)"; \
    commit="$(jq -er .commit /lock/engine.lock.json)"; \
    pkg="$(jq -er .cargo_package /lock/engine.lock.json)"; \
    bin="$(jq -er .binary /lock/engine.lock.json)"; \
    git init -q openmhs; cd openmhs; \
    git remote add origin "$repo"; \
    git fetch -q --depth 1 origin "$commit"; \
    git checkout -q FETCH_HEAD; \
    test "$(git rev-parse HEAD)" = "$commit"; \
    cargo build --release --locked -p "$pkg" -j "$CARGO_BUILD_JOBS"; \
    install -D -m 0555 "target/release/$bin" /out/bin/openmhs; \
    version="$(/out/bin/openmhs --version)"; \
    digest="sha256:$(sha256sum /out/bin/openmhs | cut -d' ' -f1)"; \
    jq -n --arg b /opt/openmhs/bin/openmhs --arg s "$digest" --arg c "$commit" --arg v "$version" \
       --arg p "linux-$(uname -m)" '{binary: $b, sha256: $s, commit: $c, version: $v, platform: $p}' > /out/build.json; \
    cat /out/build.json

# --- python dependencies (no dev group: no pgserver, no test tools) ---------------------------------------------
FROM ${UV_IMAGE} AS uv
FROM ${PYTHON_IMAGE} AS deps
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY packages/openmhs-bridge packages/openmhs-bridge
COPY packages/device-sdk packages/device-sdk
COPY services/api services/api
RUN uv sync --frozen --no-dev --package pap-api

# --- runtime ----------------------------------------------------------------------------------------------------
FROM ${PYTHON_IMAGE} AS runtime
RUN groupadd --system --gid 10001 pap \
 && useradd --system --uid 10001 --gid pap --home-dir /nonexistent --no-create-home --shell /usr/sbin/nologin pap
# Code and engine are owned by root and read-only to the service user; only /data is writable.
COPY --from=deps /app /app
COPY engine.lock.json /app/engine.lock.json
COPY --from=engine /out/bin/openmhs /opt/openmhs/bin/openmhs
COPY --from=engine /out/build.json /app/.engine/build.json
RUN mkdir -p /data/artifacts /data/work && chown -R pap:pap /data
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PAP_ENGINE_LOCK_PATH=/app/engine.lock.json \
    PAP_STORAGE_PATH=/data/artifacts \
    PAP_WORK_PATH=/data/work
WORKDIR /app/services/api
USER 10001:10001
EXPOSE 8000
# The worker uses the same image: command ["python", "-m", "app.workers.run"].
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]

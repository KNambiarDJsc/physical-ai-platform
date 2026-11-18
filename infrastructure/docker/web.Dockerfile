# syntax=docker/dockerfile:1.7
# Web application image: Next.js standalone server, run as the unprivileged `node` user.
# The API address is read at run time (PAP_API_URL) by the /api/v1 proxy route, so one image serves any API.
#
# Build context: the repository root.
#   docker build -f infrastructure/docker/web.Dockerfile -t pap-web:local .

# Newest official rebuild (D-023): 22.16.0 carried 23 fixable HIGH/CRITICAL OS findings, 22.23.5 has 0.
ARG NODE_IMAGE=node:22.23.5-bookworm-slim@sha256:e9f565d32859f0cbfb52125eafe8be39390f24dac302dc3cdf566e8ba3ab21ee

FROM ${NODE_IMAGE} AS build
ENV NEXT_TELEMETRY_DISABLED=1
WORKDIR /web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY apps/web/ ./
RUN npm run build

FROM ${NODE_IMAGE} AS runtime
# The server needs only `node`. The package managers bundled in the base image (npm, npx, corepack, yarn) are
# removed: they are never run here, and npm's own dependencies carried all 10 remaining Trivy findings.
RUN rm -rf /usr/local/lib/node_modules /usr/local/bin/npm /usr/local/bin/npx /usr/local/bin/corepack \
           /usr/local/bin/yarn /usr/local/bin/yarnpkg /opt/yarn-*
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 HOSTNAME=0.0.0.0 PORT=3000
WORKDIR /web
# Owned by root, readable by `node`: the server cannot modify its own code.
COPY --from=build /web/.next/standalone ./
COPY --from=build /web/.next/static ./.next/static
USER node
EXPOSE 3000
CMD ["node", "server.js"]

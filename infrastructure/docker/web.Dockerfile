# syntax=docker/dockerfile:1.7
# Web application image: Next.js standalone server, run as the unprivileged `node` user.
# The API address is read at run time (PAP_API_URL) by the /api/v1 proxy route, so one image serves any API.
#
# Build context: the repository root.
#   docker build -f infrastructure/docker/web.Dockerfile -t pap-web:local .

ARG NODE_IMAGE=node:22.16.0-bookworm-slim@sha256:048ed02c5fd52e86fda6fbd2f6a76cf0d4492fd6c6fee9e2c463ed5108da0e34

FROM ${NODE_IMAGE} AS build
ENV NEXT_TELEMETRY_DISABLED=1
WORKDIR /web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY apps/web/ ./
RUN npm run build

FROM ${NODE_IMAGE} AS runtime
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 HOSTNAME=0.0.0.0 PORT=3000
WORKDIR /web
# Owned by root, readable by `node`: the server cannot modify its own code.
COPY --from=build /web/.next/standalone ./
COPY --from=build /web/.next/static ./.next/static
USER node
EXPOSE 3000
CMD ["node", "server.js"]

# syntax=docker/dockerfile:1.7
FROM docker.io/library/node:24-trixie-slim AS builder

WORKDIR /app
COPY package.json package-lock.json .npmrc ./
# --no-audit/--no-fund: this resolves through Nexus (.npmrc), not npmjs.org,
# and the lockfile makes the install reproducible, same as uv.lock elsewhere.
RUN npm ci --no-audit --no-fund

COPY tsconfig.json vite.config.ts index.html ./
COPY src ./src
RUN npm run build


# nginx-unprivileged: runs as a non-root user on port 8080 out of the box,
# matching the runAsNonRoot security context every other workload in this
# platform runs under (see services/order-api/Dockerfile).
FROM docker.io/nginxinc/nginx-unprivileged:1.27-alpine AS runtime
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 8080

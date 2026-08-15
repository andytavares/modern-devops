---
type: tool
tags: [language, application]
role: order-worker — the Kafka consumer
version: Go 1.26.x
docs: https://go.dev/doc/
date_added: 2026-08-15
date_updated: 2026-08-15
status: in-use
---

# Go

> [!info] One-liner
> Statically compiled, no runtime to ship — which is what makes a 2 MB distroless container image possible.

## What it does here

`services/order-worker` (§3.2): consumes the `orders` topic, writes to DynamoDB via [[floci]],
exposes `/healthz`, `/readyz` and `/metrics` on port 9090.

Built as `CGO_ENABLED=0 GOOS=linux` with `-trimpath` and `-ldflags="-s -w -X main.version=..."`,
producing a static binary that runs on `gcr.io/distroless/static-debian12:nonroot`.

## Key concepts

- **`CGO_ENABLED=0`** yields a genuinely static binary — the precondition for scratch/distroless.
- **`-X main.version`** stamps the build SHA into the binary at link time, so a running process can
  report which commit it is. Cheap, and invaluable during an incident.
- **Graceful shutdown matters here**: on SIGTERM the worker must finish its in-flight batch and commit
  offsets, hence `terminationGracePeriodSeconds: 45`.
- Module proxying via `GOPROXY` → [[sonatype-nexus]], with `GOSUMDB=off` because the public checksum
  database is unreachable through a private proxy.

## Official docs

- Docs: https://go.dev/doc/
- Modules and GOPROXY: https://go.dev/ref/mod
- Distroless base images: https://github.com/GoogleContainerTools/distroless

> [!tip] Related
> [[apache-kafka]], [[floci]], [[sonatype-nexus]], [[order-platform]]

---
type: tool
tags: [language, application]
role: order-worker — the Kafka consumer
version: Go 1.26.x
docs: https://go.dev/doc/
date_added: 2026-08-15
date_updated: 2026-08-16
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

## `-race` needs cgo, so test and build want different images

The race detector is implemented with a C runtime, so `go test -race` requires cgo — the exact
opposite of what the release build wants.

| Image | `CGO_ENABLED` | C toolchain | Use |
|---|---|---|---|
| `golang:1.26-alpine` | `0` | none | **build** (§3.2 Dockerfile) — static binary for distroless |
| `golang:1.26` | `1` | gcc 14.2.0 | **test** (§12.5) — `go test -race` |

Verified 2026-08 by running both images: `go env CGO_ENABLED` returns `0` and `1` respectively, and
`gcc` is absent from the alpine image. `golang:1.26` also ships git 2.47.3, so the `apk add git` line
the alpine step needed disappears.

> [!warning] Hit in CI 2026-08-15
> ```
> go: -race requires cgo; enable cgo by setting CGO_ENABLED=1
> ```
> Setting `CGO_ENABLED=1` alone does **not** fix it on alpine — there is no compiler for cgo to
> invoke. Either add `gcc musl-dev` to the alpine step or switch the test image to Debian. The
> Dockerfile should stay on alpine: `CGO_ENABLED=0` is the precondition for the distroless image.

## Official docs

- Docs: https://go.dev/doc/
- Modules and GOPROXY: https://go.dev/ref/mod
- Distroless base images: https://github.com/GoogleContainerTools/distroless

> [!tip] Related
> [[apache-kafka]], [[floci]], [[sonatype-nexus]], [[order-platform]]

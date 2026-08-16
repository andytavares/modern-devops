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
exposes `/healthz`, `/readyz` and `/metrics` on port 9090. Go [[grpc]] stubs for `shop.v1.Pricing`
are generated for it from `protos/shop/v1/pricing.proto` by the same target that generates the Python
ones (§18.1).

Built as a static binary that runs on `gcr.io/distroless/static-debian12:nonroot`. Since the
[[pants]] migration the compile happens under `pants package services/order-worker:bin`
(`go_mod` / `go_package` / `go_binary`) and the Dockerfile just `COPY`s the result — `CGO_ENABLED=0`
is set by the Go backend's default toolchain env rather than in the Dockerfile.

> [!warning] The `-X main.version` claim on this page was wrong — corrected 2026-08-16
> **What this page said:** *"`-X main.version` stamps the build SHA into the binary at link time, so
> a running process can report which commit it is."* §3.2 said the same thing about
> `-ldflags="-s -w -X main.version=${VERSION}"`.
>
> **What is true:** `-X importpath.name=value` sets a **string variable that already exists** in the
> compiled package. `services/order-worker/main.go` declares no `var version string`; it reads the
> environment — `version: getenv("SERVICE_VERSION", "dev")`. When the symbol is absent Go's linker
> does not error and does not warn. **It silently does nothing.**
>
> So the `ARG VERSION`, the `--build-arg VERSION=$SHA`, and the `BUILD_ARGS` special case in the
> pipeline were plumbing for a mechanism that never ran. Nothing looked broken because the version a
> running worker reports has always come from `SERVICE_VERSION`, which the chart sets from the image
> tag (§10.1).
>
> **Which source won and why:** the source code. Both the tutorial and this page asserted a link-time
> stamp; `main.go` has no symbol for `-X` to write to, and Go's linker behaviour on a missing symbol
> is a no-op by design. The pipeline plumbing has been deleted rather than repaired.
>
> `-s -w` and `-trimpath` were and are real. Only the `-X` was inert.
>
> **The transferable lesson: `-X` fails open.** A flag that misconfigures silently while still
> producing a plausible artifact needs a test that asserts the *outcome* — one
> `assert version != "dev"` in a smoke test would have caught this on day one.

## Key concepts

- **`CGO_ENABLED=0`** yields a genuinely static binary — the precondition for scratch/distroless.
- **Version reporting is an environment variable, not a linker flag.** `SERVICE_VERSION`, set by the
  chart from the image tag. Pants' `go_binary` does support `linker_flags`, so a real `-X` stamp is
  reinstatable — but it would need a `var version` in `main.go` and a test, and one working mechanism
  beats two.
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
> [[apache-kafka]], [[floci]], [[sonatype-nexus]], [[order-platform]], [[pants]], [[grpc]]

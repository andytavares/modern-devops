---
type: tool
tags: [language, service]
role: order-worker
version: 1.26.5 in go.mod; the CI image pins golang:1.26.6 with GOTOOLCHAIN=local
docs: https://go.dev/doc/
date_added: 2026-08-17
date_updated: 2026-08-17
status: in-use
---

# Go

> [!info] One-liner
> order-worker: consumes the `orders` topic, writes to DynamoDB, exports metrics. Its interesting content is the commit boundary and the static-linking constraint.

## The service

`services/order-worker/` — [[franz-go]] for Kafka, `aws-sdk-go-v2` for DynamoDB,
`prometheus/client_golang` for metrics. Config from the environment with two required variables
(`KAFKA_BROKERS`, `DDB_TABLE`) that fail startup when absent.

Metrics: `orders_processed_total{result}`, `order_process_duration_seconds`,
`order_event_age_seconds` — that last is the in-band consumer-lag proxy this platform alerts on.

## `run() error`, not a `main` full of `os.Exit(1)`

`os.Exit` **skips every deferred call**, so a `main` that exits inline never runs `client.Close()` and
never commits. Pushing the work into `run()` gives one exit point, after the defers.

The metrics server gets the same treatment through `context.WithCancelCause`: a failure to bind `:9090`
cancels the consume loop and the cause carries the reason out to `main`, instead of being logged by a
goroutine nobody is watching **while the pod stays happily ready**.

SIGTERM is handled via `signal.NotifyContext` — it is what Kubernetes sends first on pod deletion, and
handling it is the difference between a graceful rolling update and dropped in-flight work.
`terminationGracePeriodSeconds: 45` in the chart is what allows time for it.

## Static linking is a hard requirement, twice over

`gcr.io/distroless/static-debian12:nonroot` has neither libc nor a dynamic loader.

The hand-written Dockerfile set `CGO_ENABLED=0` for this reason. **Moving the build into [[pants]]
silently dropped it** — Pants defaults `[golang] cgo_enabled` to *true* — and the pod died with
`exec /order-worker: no such file or directory` on a file that is present and executable. **It is the
loader that is missing, not the binary.** Check with `readelf -l <binary> | grep interpreter`: a static
binary has no `PT_INTERP`. `pants.toml` now sets `cgo_enabled = false` with the reasoning inline. See
[[cross-compilation]].

This is also why [[franz-go]] was chosen over `confluent-kafka-go`, which wraps librdkafka.

> [!warning] `go test -race` needs cgo, so the test and the build want opposite things
> `golang:1.26-alpine` is `CGO_ENABLED=0` with no gcc, and `-race` is implemented with a C runtime —
> setting the variable alone does not help, because there is no compiler. The test step uses
> `golang:1.26` (Debian); the Dockerfile still builds `FROM golang:1.26-alpine` and should. One
> toolchain, two opposite requirements (§12.5).

> [!warning] The Go toolchain patch version is pinned, not just the minor
> `go.mod` says `go 1.26.5` and the CI image sets `GOTOOLCHAIN=local`, forbidding a download. A
> floating `golang:1.26` that ever resolves below 1.26.5 turns every Go build into
> `go.mod requires go >= 1.26.5`. `.buildkite/pants-ci.Dockerfile` copies from `golang:1.26.6`.

## Checksum verification stays on

`GOPROXY` points at [[sonatype-nexus]]' `go-proxy` and **nothing else is overridden**. `go.sum` records
a hash for every module in the build list, so `go` verifies locally and never consults the checksum
database during a build. `GOFLAGS=-mod=readonly` is already Go's default and is stated because it is
load-bearing: under `-mod=mod` a build may rewrite `go.mod` and succeed against a dependency set nobody
committed. See [[supply-chain-choke-point]].

## A correction worth keeping

> [!warning] `-ldflags "-X main.version=…"` never stamped anything
> §3.2 and this page previously both carried that claim. `main.go` has no such symbol, so the flag was
> a no-op the whole time. The version a running service reports comes from `SERVICE_VERSION`, set by
> the chart from the image tag — one mechanism applied uniformly to Python and Go alike, rather than a
> Go-specific link-time stamp only one of four images could carry. §19.5 removed the last
> `--build-arg` from the pipeline.

## Related

[[franz-go]] · [[apache-kafka]] · [[at-least-once-delivery]] · [[pants]] · [[cross-compilation]] · [[floci]] · [[prometheus]]

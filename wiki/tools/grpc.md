---
type: tool
tags: [rpc, protobuf, python, go, istio]
role: The synchronous contract between order-api and pricing, and the shared schema for two languages
version: grpcio (pinned by locks/python-default.lock); protobuf syntax proto3
docs: https://grpc.io/docs/
date_added: 2026-08-16
date_updated: 2026-08-16
status: in-use
---

# gRPC

> [!info] One-liner
> An RPC framework over HTTP/2 whose interface is a compiled artifact rather than a convention — which is the only reason a schema change can fail two languages in one command.

## What it is

Protocol Buffers define messages and services in a `.proto`; `protoc` compiles that into native code
for each language; the generated stubs speak a binary wire format over HTTP/2. The parts that matter
operationally: HTTP/2 multiplexing (many concurrent requests on one connection), per-call
**deadlines** propagated in metadata, and a status code enumeration richer than HTTP's.

## What it does here

One file — `protos/shop/v1/pricing.proto` — defines `shop.v1.Pricing/PriceOrder` and generates
**Python and Go stubs from a single [[pants]] target** (§18.1):

```python
protobuf_sources(name="protos", sources=["*.proto"], grpc=True)
```

`grpc=True` is load-bearing. Without it protoc emits message classes only and the service stub never
appears.

`services/pricing` serves it on port 50051. `services/order-api` calls it on the order path with a
`grpc.aio` client and a **2 second deadline**, returning HTTP 502 on failure with no fallback (§19.1).
`services/order-worker` gets Go stubs from the same target.

**This is the first synchronous service-to-service hop in the platform.** Until it existed,
`order-api` and `order-worker` were joined only by [[apache-kafka]] and never called each other —
which is why §9.1 is blunt that the mesh had no request path to secure between them. Retries,
timeouts, traffic shifting and outlier detection only mean something once there is a call to apply
them to. See [[istio]].

## The cross-language check is the whole point

Change a field name in the `.proto` and run `pants check ::`: Python fails on the attribute and Go
fails to compile, in the same command, in seconds. The previous arrangement — a JSON shape agreed in
code review and re-declared in two languages — surfaced the same mistake as a decode error in a
consumer, after the message was already durable in Kafka.

The argument for a monorepo is not tidiness. It is that **a shared interface can be checked by a
compiler across language boundaries**, and that check requires one build system seeing both sides.
Split the repo and you are back to versioned artifacts, publish ordering, and a window during which
the two sides disagree.

## Istio routes gRPC by the Service **port name**

> [!warning] Wrong port name means silent TCP passthrough and no L7 routing at all
> There is no `grpc:` stanza in a `VirtualService` — gRPC rides HTTP/2 and is routed by the ordinary
> `http:` block. What makes [[istio]] treat a Service's traffic as HTTP/2 with gRPC semantics is the
> **name of the port**: the `grpc` / `grpc-*` prefix maps to HTTP/2.
>
> ```yaml
>   ports:
>     - { name: grpc, port: 50051, targetPort: grpc }
> ```
>
> Name it `pricing` or `tcp-grpc` and Istio falls back to plain TCP passthrough. Weights, retries,
> timeouts and gRPC-status-aware outlier detection are all L7 features and none of them apply. **The
> manifests still apply cleanly, [[kiali]] still draws a line, and traffic still flows** — it just
> flows round-robin, ignoring every number you wrote. A config that applies successfully and does
> nothing is worse than one that fails.
>
> Check: `kubectl -n shop get svc pricing -o jsonpath='{.spec.ports[*].name}'`, or
> `istioctl analyze -n shop`.

## Deadlines are the thing to design around

A gRPC deadline is a client-side budget propagated to the server, not a server-side setting. Every
Istio number for `pricing` is derived inward from `order-api`'s 2000 ms deadline: a 1800 ms route
timeout so Envoy gives up first and returns a deterministic error rather than racing the client's
timer, and a retry envelope (3 attempts × 500 ms + backoff ≈ 1550 ms) that fits inside both ceilings.
§9.8 has the arithmetic.

`retryOn` deliberately excludes `deadline-exceeded` (the budget is already spent) and
`resource-exhausted` (retrying hammers a struggling pod — ejecting it is outlier detection's job).
**Retry only what a different pod would plausibly answer.**

## Generated Python needs help from mypy

> [!warning] mypy reports the generated message classes do not exist, and it is right
> `pricing_pb2.py` calls `_builder.BuildTopDescriptorsAndMessages(...)`, which creates the classes in
> `globals()` at import time. Statically there is no `class PriceOrderRequest`, so mypy says so.
>
> Fix: `generate_type_stubs = true` under `[python-protobuf]`, which has protoc emit a `.pyi` beside
> each `_pb2.py`. Pants' own help prefers this to the older mypy-plugin option.
>
> Separately, **`grpcio` ships no `py.typed` marker**, so mypy cannot see its types at all regardless
> of stubs. `types-grpcio` is the fix and mypy's own suggestion to install it is correct. Verified by
> checking `pants export --resolve=python-default` for a `py.typed` under `grpc/` — there isn't one.

## Key concepts

- **Health checking is HTTP here, not gRPC.** `pricing` runs a small stdlib HTTP server on 9090 for
  `/healthz`, `/readyz` and `/metrics` — Kubernetes probes and [[prometheus]] both want HTTP, and
  gRPC health checking is a larger dependency than this needs.
- **Money is `int32` cents** throughout the schema. Floating-point currency is a bug you ship once.
- **`served_by` is a free-form string on the wire**, not a closed `v1`/`v2` union. The frontend's
  tally keys on whatever actually came back, so an unexpected value becomes its own bucket instead of
  inflating an existing one — a dashboard whose job is showing a ratio must not have a fallback
  bucket. See [[vite]].
- **Field numbers, not field names, are the wire contract.** Renaming is safe; renumbering is not.

## Why this, not the alternative

vs **REST/JSON**: what `order-api` exposes at the edge, and the right call there — browsers and curl
speak it. Between services it gives you no compiler-checked contract, which is the entire reason this
exists.
vs **an event on [[apache-kafka]]**: already used for `order-api` → `order-worker`, and correct for
that hop because the work is asynchronous. Pricing must return a number before the response is
written, so it is a request, not an event. **Do not make a synchronous dependency asynchronous to
avoid coupling — you get the coupling plus a correlation problem.**
vs **OpenAPI-generated clients**: a real option with a real schema, but the codegen story across
Python and Go is looser and the wire format is not the schema.

## Official docs

- Docs: https://grpc.io/docs/
- Deadlines: https://grpc.io/docs/guides/deadlines/
- Status codes: https://grpc.io/docs/guides/status-codes/
- Protocol Buffers: https://protobuf.dev/
- Istio protocol selection: https://istio.io/latest/docs/ops/configuration/traffic-management/protocol-selection/
- Pants protobuf/Python: https://www.pantsbuild.org/stable/docs/python/integrations/protobuf-and-grpc

> [!tip] Related
> [[pants]], [[istio]], [[fastapi]], [[go]], [[apache-kafka]], [[order-platform]], [[service-mesh]], [[vite]]

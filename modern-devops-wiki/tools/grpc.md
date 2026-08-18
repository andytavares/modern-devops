---
type: tool
tags: [protocol, contract, polyglot]
role: one .proto compiled into two languages; the first synchronous hop in the platform
version: protobuf sources via pants 2.33.0 codegen; grpcio + grpcio-health-checking + grpcio-reflection
docs: https://grpc.io/docs/
date_added: 2026-08-17
date_updated: 2026-08-17
status: in-use
---

# gRPC and Protocol Buffers

> [!info] One-liner
> `protos/shop/v1/pricing.proto` is the contract. [[pants]] compiles that one file into the Python server, the Python client and the Go stubs, so a change to it fails on your laptop in ten seconds instead of at runtime in a consumer.

## The problem it solves

order-api and order-worker share a data model **by convention**: a JSON shape agreed in a code review
and re-declared in two languages. Nothing catches it when one side changes. The failure lands at
runtime, in a cluster, as a decode error on a message already committed to [[apache-kafka]] (§17).

The demonstration that justifies the whole phase: rename `quantity` to `qty` in the `.proto` and run
`pants check ::`. Python fails on the attribute and Go fails to compile, in the same command.

> **This is the entire argument for a monorepo, and it is not "one repo is tidier".** It is that a
> shared interface can be **checked by a compiler across language boundaries**, and that check is only
> possible when one build system sees both sides. Split the repo and you are back to versioned
> artifacts, publish ordering, and a window during which the two sides disagree (§18.2).

## The contract

`shop.v1.Pricing/PriceOrder`, request `{sku, quantity, unit_amount_cents, customer}`, response
`{total_amount_cents, discount_cents, rule_applied, served_by}`.

**`served_by` is the field this platform is built around**: the pricing implementation writes its own
version into it, order-api passes it through as `priced_by`, and [[vite]]'s dashboard tallies it. That
is what makes an [[istio]] weight change something you *watch* rather than infer from a metric.

**Money is `int32` cents throughout.** Floating-point currency is a bug you ship once.

`protos/shop/v1/BUILD` is one target for both language backends:

```python
protobuf_sources(name="protos", sources=["*.proto"], grpc=True)
```

`grpc=True` is not decoration — without it protoc emits message classes only and the `Pricing` service
stub never appears.

Generated files are **not committed**. `pants export-codegen` exists so you can read them once;
`check`, `test` and `package` generate into a sandbox on demand.

## Three first-party protocols on one port (§19.1)

`pricing` serves the application service, the **health checking protocol** (`grpc.health.v1`) and
**server reflection**, all on 50051. Port 9090 carries Prometheus metrics and nothing else.

**There is no hand-rolled HTTP server, and there must not be one.** A gRPC server answering probes over
a second protocol on a second port asserts that the HTTP listener and the gRPC listener fail together,
which is not true — a saturated gRPC thread pool leaves the HTTP thread answering `200` for a server
that cannot serve an RPC. The kubelet speaks the health protocol itself, so the probe and the traffic
take the same path. See [[health-checks]].

Three load-bearing details in `build_server()`:

- **Every service name is registered explicitly, including the empty one.** The empty name carries
  overall health and is what a `grpc:` probe with no `service:` field asks for. A name never registered
  answers `NOT_FOUND`, not `NOT_SERVING`.
- **Service names come off the generated descriptors** —
  `pricing_pb2.DESCRIPTOR.services_by_name[...]`, not string literals — so renaming in the `.proto`
  cannot leave a stale name registered. order-api derives `PRICING_SERVICE_NAME` the same way.
- **Reflection needs its own name in its own list.** Python's reflection has no automatic discovery.

`build_server()` binds no port and starts no thread, which is what lets the tests stand up the exact
server the process runs on an ephemeral port. Health and reflection are **wire** protocols — an
in-process assertion would prove nothing about what a kubelet or `grpcurl` sees.

**`context.abort()` raises**, ending the RPC in one call. `set_code`/`set_details` followed by `return`
arrives at the caller as a *successful empty response*.

## The client side

One channel per process, built in the lifespan and drained on shutdown. A gRPC channel is a
long-lived multiplexing object managing its own connection pool; one per request throws away the
connection and pays a TCP and HTTP/2 handshake on every order.

`insecure_channel` is correct here: the [[istio]] sidecar terminates [[mtls]], so TLS in the
application would be a redundant second layer. The `timeout=` argument **is** the deadline — without
it a synchronous hop turns a slow dependency into an outage.

**One gRPC status, one HTTP status.** `DEADLINE_EXCEEDED` → 504, `UNAVAILABLE` → 503,
`INVALID_ARGUMENT` → 400, `RESOURCE_EXHAUSTED` → 429, anything unlisted → 502. Collapsing them all to
502 tells the caller that a timeout, an overload and a malformed order are the same thing. A
parametrised test pins the table.

**No fallback, deliberately.** A locally computed price is the kinder production design — the customer
gets an order instead of an error — and it would make every experiment in §9.8 invisible. **A fallback
that is not itself alarmed on is a way of not finding out.** If you add one, add
`pricing_calls_total{result="fallback"}` and an alert on it *in the same commit*.

## The port must be named `grpc`

There is no `grpc:` stanza in a `VirtualService` — gRPC rides HTTP/2 and is routed by the ordinary
`http:` block. What tells Istio to treat the Service as HTTP/2 with gRPC semantics is the **port
name**. Name it anything else and Istio guesses, and on a bad guess weights, retries, timeouts and
gRPC-status-aware outlier detection simply do not apply while the manifests still apply cleanly and
traffic still flows round-robin. See [[port-naming]].

## Related

[[pants]] · [[istio]] · [[mypy]] · [[fastapi]] · [[health-checks]] · [[timeouts-and-retries]] · [[vite]] · [[backstage]]

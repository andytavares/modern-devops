---
type: concept
tags: [kubernetes, operations, reliability]
date_added: 2026-08-17
date_updated: 2026-08-17
---

# Health checks

> [!info] One-liner
> Liveness means "the process is alive". Readiness means "my dependencies are up". Conflating them turns a downstream outage into every pod being killed.

## Three probes, three jobs

| Probe | Question | Failure action |
|---|---|---|
| `startupProbe` | has it finished booting? | keeps liveness from firing during a slow start |
| `livenessProbe` | is the process wedged? | **kill the container** |
| `readinessProbe` | can it serve right now? | **pull it out of the Service** |

`startupProbe` is the one people omit. order-api gives it `failureThreshold: 20` at `periodSeconds: 3`
— up to 60s to boot — **without loosening liveness**, which stays tight so a genuinely wedged pod is
killed fast. Loosening liveness to cover a slow start is the mistake it exists to prevent.

## Liveness must check nothing else

```python
@app.get("/healthz")
def healthz() -> dict:
    """Liveness: the process is running. Deliberately checks nothing else."""
```

A test pins it: *"Liveness must answer without Kafka or S3, or a broker outage kills every pod."* If
liveness checks a dependency, a shared dependency failing restarts your entire fleet — turning a
partial outage into a total one, and adding a thundering herd to it.

## Readiness is allowed to know about dependencies, and should

order-api's `/readyz` returns 503 when the lifespan has not completed **or when [[grpc]] `pricing` is
not serving**. If pricing is down this pod cannot serve orders and should be pulled from the Service
rather than answering errors.

> [!warning] Readiness must ask over the wire; channel state is a lie
> `get_state()` reports what the local gRPC channel object believes about its own connectivity, and a
> channel that has never reached anything is `IDLE` or `CONNECTING` — both of which look fine, and
> neither of which means a call would succeed. **A backend that does not exist at all reads as ready.**
>
> `Check` is a real RPC: it either comes back `SERVING` inside the deadline or it does not. A
> parametrised test asserts that `NOT_SERVING`, `SERVICE_UNKNOWN` and `UNKNOWN` are all not-ready.

**The health probe needs its own, shorter deadline.** `pricing_health_timeout_seconds` is separate from
`pricing_timeout_seconds` because readiness must answer on the *probe's* schedule, not the order path's
— and without a deadline a probe against a hung backend hangs with it, leaving the kubelet's own
timeout as the only thing that ends the request.

## The kubelet speaks gRPC health itself

`pricing`'s probes are `grpc:`, not HTTP. No `grpc_health_probe` binary in the image, no second
listener.

> **A gRPC server that answers probes over a second protocol on a second port is asserting that the
> HTTP listener and the gRPC listener fail together, which is not true** — a saturated gRPC thread pool
> leaves the HTTP thread answering `200` for a server that cannot serve an RPC. Probe and traffic take
> the same path, or the probe is measuring the wrong thing.

Liveness asks for the **empty** service name (overall health, what a `grpc:` probe with no `service:`
field requests); readiness names `shop.v1.Pricing`. **Every name a probe may ask for must be
registered**, including the empty one — a name never registered answers `NOT_FOUND`, not `NOT_SERVING`.

`GRPCAction.port` is an `int32`, not an `IntOrString`, so a port **name** is rejected by the API server.

## Graceful shutdown is part of readiness

On SIGTERM, `health_servicer.enter_graceful_shutdown()` flips every registered service to `NOT_SERVING`
**before** `server.stop()` closes the listener, so readiness sees the pod leaving while it can still
answer. order-worker does the equivalent through `signal.NotifyContext` and its deferred
`client.Close()`, which is why `terminationGracePeriodSeconds: 45` exists — see
[[at-least-once-delivery]].

## `NOT_FOUND` and `UNIMPLEMENTED` are treated as ready, deliberately

gRPC's own documentation requires clients to cope with a server that does not publish health, and **a
server that answered with a status is by definition reachable.** That is "health unknown", not "health
failing".

## Related

[[grpc]] · [[fastapi]] · [[kubernetes]] · [[pydantic]] · [[order-platform]] · [[at-least-once-delivery]] · [[observability]]

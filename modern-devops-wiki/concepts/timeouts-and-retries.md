---
type: concept
tags: [reliability, networking, service-mesh]
date_added: 2026-08-17
date_updated: 2026-08-17
---

# Timeouts, retries and outlier detection

> [!info] One-liner
> Every number in `pricing-traffic.yaml` is derived inward from one fact: order-api sets a 2000 ms client-side gRPC deadline and returns 502 with no fallback when it expires.

## The route timeout is deliberately *less* than the caller's deadline

**1800 ms against a 2000 ms deadline.** A route timeout longer than the caller's is pointless —
order-api's own timer fires at 2000 ms regardless, so everything Envoy does past that point is work for
a caller who has already given up.

Setting it 200 ms **under** means Envoy is the one that gives up, returning a clean
`upstream request timeout`. Set them **equal** and the two timers race to fire at the same instant,
making the failure mode nondeterministic — sometimes a proxy-side error, sometimes a bare
`DEADLINE_EXCEEDED` from the gRPC library. **A failure you cannot reproduce is a failure you cannot
alert on.**

## The retry envelope must fit inside both ceilings

```
  3 attempts (1 initial + 2 retries) × 500 ms perTryTimeout   = 1500 ms
+ 2 backoff gaps × ~25 ms minimum                             =   50 ms
                                                              ─────────
  worst case                                                  ≈ 1550 ms

  1800 ms route timeout    − 1550 ms  =  ~250 ms slack
  2000 ms client deadline  − 1550 ms  =  ~450 ms slack
```

`attempts: 2` in Istio means two **retries**, so three attempts total. Istio also applies exponential
backoff between attempts — easy to omit from the sum, and exactly big enough to matter when the slack
is 250 ms.

> **Retries that can outlive the caller's deadline are worse than no retries at all.** They burn the
> budget on attempts whose results nobody will ever see, while the caller has already returned an
> error. **If you change `perTryTimeout`, redo the sum** — this is the number people bump to "give it a
> chance" and thereby guarantee the timeout they were trying to avoid.

## `retryOn` is narrow on purpose

**Retried** — `unavailable`, `cancelled` (transient and connection-level, matching Istio's own default
set), `connect-failure`, `refused-stream` (HTTP/2-level: the request never reached an application
handler, so retrying is safe and cheap).

**Not retried** — `deadline-exceeded` (already spent its per-try budget once), `resource-exhausted` and
`internal` (the instance is already overloaded or broken; **that is outlier detection's job — eject it
— not a retry's**).

> **Retry only what a *different pod* would plausibly answer.** Everything else is a load amplifier
> attached to a service that is already failing, which is how a small incident becomes a large one.

## Two outlier-detection defaults that had to change

| Field | Istio default | Here | Why |
|---|---|---|---|
| `consecutive5xxErrors` | 5 | **3** | With 2–3 replicas per subset, one bad pod serves a large share of volume. 5 is too much blast radius; 1–2 trips on ordinary transient errors. |
| `maxEjectionPercent` | 10% | **50%** | **10% of a 2-replica pool rounds down to zero ejectable hosts.** |

> That second row is the one to remember. **Outlier detection's defaults assume a pool much larger than
> a laptop cluster's**, and a percentage that rounds to zero produces a feature that reports as enabled
> and never fires. Nothing warns you.

`baseEjectionTime: 30s` stays at the default — long enough that an ejected pod is not reconsidered on
the very next 15s sweep, short enough that a blip self-heals without an operator.

`maxRequestsPerConnection: 0` (unlimited per HTTP/2 connection): HTTP/2 is designed for long-lived
multiplexed connections, and forcing reconnects adds handshake latency inside a 2 second budget for no
gRPC-specific benefit.

## The drill, and the lesson hiding in it

§9.10 injects a **3 second delay into 50% of calls** — chosen to beat every timer in the chain, so
neither the 1800 ms route timeout nor the 2000 ms deadline can rescue it. *The point of a drill is a
real, visible failure, not a near-miss that leaves you unsure whether anything happened.*

The subtle result: **a client-side injected delay registers in order-api's own sidecar as a gateway
timeout against the `pricing` cluster**, so it counts toward `consecutive5xxErrors` and Envoy starts
ejecting pricing pods **that are perfectly healthy.** The fault is in the proxy, not the pod, and
outlier detection cannot tell the difference.

> **That is not a bug in the drill; it is the lesson.** Outlier detection ejects on *observed symptoms*,
> and a symptom seen at the client cannot distinguish "this pod is sick" from "the path to this pod is
> sick". In production this is how a network problem becomes a capacity problem: every client
> independently decides the backends are bad, and a service with no failing pods loses half its pool.

## The client side sets the ceiling

A `timeout=` on the gRPC call is not optional. Without it a synchronous hop turns a slow dependency
into an outage — every request parks on the event loop until the client gives up, and order-api stops
answering for reasons that have nothing to do with order-api. See [[grpc]] and [[health-checks]].

## Status

**Never run against a live cluster.** §9.9 and §9.10 are written from the manifests and their reasoning;
every manifest passes `kubectl apply --dry-run=server`. See [[open-questions]].

## Related

[[istio]] · [[grpc]] · [[service-mesh]] · [[health-checks]] · [[pydantic]] · [[port-naming]] · [[observability]]

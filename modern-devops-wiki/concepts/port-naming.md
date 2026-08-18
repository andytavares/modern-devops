---
type: concept
tags: [networking, kubernetes, observability]
date_added: 2026-08-17
date_updated: 2026-08-17
---

# Port names are an interface

> [!info] One-liner
> A Kubernetes port name looks like documentation. In this platform it is a load-bearing declaration read by [[istio]] and by [[prometheus]] — and getting it wrong fails silently in both.

## Istio reads the protocol off the name

The grammar is `protocol[-suffix]`. The part **before the first hyphen** must be a protocol Istio
recognises — `http`, `http2`, `https`, `grpc`, `grpc-web`, `tcp`, `tls`, plus experimental
`mongo`/`mysql`/`redis` — and the suffix is yours.

Note the order: **`http-metrics` is valid, `metrics-http` is not.**

A name Istio does not recognise does not fail. It falls back to **automatic protocol detection**, which
sniffs the opening bytes of each connection. That is a guess, made per connection; it is wrong for
anything server-speaks-first, it adds a step to connection setup, and it leaves you no declared
protocol to reason about when telemetry looks off. `istioctl analyze` reports it as **IST0118, "Port
name is not under naming convention"** — which is why that command is in the tutorial rather than
decoration.

`appProtocol` is the explicit equivalent and **takes precedence over the name** where both are set.

## What a bad guess actually costs

Lose HTTP and you lose the L7 features that are the reason you installed a mesh: per-route routing,
retries, timeouts, and `istio_requests_total` **with a response code in it**.

For `pricing` the stakes are higher, because **there is no `grpc:` stanza in a `VirtualService`** —
gRPC rides HTTP/2 and is routed by the ordinary `http:` block. What tells Istio to apply gRPC semantics
is the port being named `grpc`. Name it anything else and weights, retries, timeouts and
gRPC-status-aware outlier detection **simply do not apply**, while the manifests apply cleanly and
traffic still flows round-robin. See [[timeouts-and-retries]].

## Prometheus selects by name, and skips a name that does not exist

> [!warning] Rename a port, forget the monitor, and the target does not error — it disappears
> A `ServiceMonitor` selects by port **name**. `servicemonitor.yaml` therefore lists one endpoint per
> port name in use (`http` for order-api, `http-metrics` for order-worker and pricing) for exactly this
> reason. Same failure mode as §9.6's silent scrape loss, different cause. See [[observability]].

And the inverse trap: the merged-metrics endpoint on **15020 is unnamed** in the pod spec, so `port:`
cannot address it and `portNumber:` is required. The port that *does* carry a name —
`http-envoy-prom`, 15090 — serves Envoy-only metrics, so selecting by name gets you a working
[[kiali]] and no application metrics at all.

## Rename in every place at once

The `containerPort`, the Service `port` name, its `targetPort`, and any probe addressing the port by
name. **A half-rename compiles and deploys** — Kubernetes only fails the probe at runtime. That is one
of the three assertions in `checks/verify_chart.py` ([[order-platform]]).

Nothing in Istio reads the *container* port name; it carries the same name so the probes and the
Service refer to one thing.

## Where this bites

§10.1 names order-worker's port `http-metrics` rather than `metrics` — in Phase 1, **three phases
before [[istio]] exists.** That is deliberate: renaming a port later means editing the Service, the
probes and every monitor that selects by name.

```bash
kubectl -n shop get svc pricing -o jsonpath='{.spec.ports[*].name}'
istioctl analyze -n shop
```

## Related

[[istio]] · [[prometheus]] · [[observability]] · [[grpc]] · [[order-platform]] · [[kiali]] · [[health-checks]]

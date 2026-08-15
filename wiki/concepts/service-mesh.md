---
type: concept
tags: [networking, security]
docs: https://istio.io/latest/docs/concepts/
date_added: 2026-08-15
date_updated: 2026-08-15
---

# Service mesh

> [!info] One-liner
> Move connection-level concerns — encryption, identity, retries, telemetry — out of application code and into a proxy beside every workload.

## What it actually gives you

1. **Identity** — every workload gets a cryptographic identity from its ServiceAccount ([[mtls]]).
2. **Authorization** — allow/deny by *identity*, not IP.
3. **Telemetry** — L7 metrics for calls whose code you don't control (our AWS SDK calls to [[floci]]
   are the interesting case: per-route latency and errors without touching either service).
4. **Traffic control** — retries, timeouts, canaries, fault injection.

## What it does not give you

- **It cannot see async paths.** order-api and order-worker are joined by [[apache-kafka]], so no mesh
  graph will ever draw an edge between them. A service graph is not an architecture diagram.
- **It is not NetworkPolicy.** The mesh authorizes *requests* by identity; NetworkPolicy filters
  *packets* by address. A workload outside the mesh is unconstrained by the mesh. Use both.
- **It does not make you secure at the edge.** Browser → nginx is still whatever TLS you configured.

## Sidecar vs ambient

| | Sidecar | Ambient |
|---|---|---|
| Data plane | Envoy per pod | one `ztunnel` per node (+ waypoint for L7) |
| Cost | ~50–100 MB **per pod** | roughly per-node |
| Enrolling | restart every pod | no restart |
| L7 policy | works immediately | needs an explicit waypoint |
| Docs/examples | deepest | growing |

This project takes sidecars for documentation depth; ambient is the better laptop choice under RAM
pressure (§9.1).

## The costs nobody mentions until you hit them

- Every Job in an enrolled namespace hangs, because the sidecar outlives the job container.
- `kubectl port-forward` stops working against STRICT namespaces.
- Prometheus can no longer scrape app ports directly — see [[observability]] and §9.6.
- Your delivery and observability tooling should probably stay *out*, so a mesh misconfiguration
  doesn't remove the tools you'd diagnose it with.

> [!tip] Related
> [[istio]], [[mtls]], [[kiali]], [[observability]], [[ingress-nginx]]

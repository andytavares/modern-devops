---
type: tool
tags: [application, chart]
role: The application this whole platform exists to deliver
version: chart 0.1.0
docs: n/a — local chart at deploy/charts/order-platform
date_added: 2026-08-15
date_updated: 2026-08-15
status: in-use
---

# order-platform (the application + its chart)

> [!info] One-liner
> Two services and a Helm chart, deliberately small so the platform is the star.

## The business flow

1. `POST /orders` hits **order-api** ([[fastapi]], Python).
2. order-api writes raw JSON to **S3** ([[floci]]) and produces to the **`orders`** topic ([[apache-kafka]]).
3. **order-worker** ([[go]]) consumes and writes a row to **DynamoDB**.
4. Both export Prometheus metrics; [[grafana]] shows it end to end.

Two languages on purpose: a real platform is polyglot, and the interesting problems — image builds,
dependency proxying, health checks, metrics conventions — only get interesting when runtimes differ.

## The chart

`deploy/charts/order-platform` ([[helm]], §10.1) renders:

- a `ServiceAccount` per workload — **required**, because [[istio]]'s authorization policies key on
  them and `default` is not an identity
- Deployment + Service (+ Ingress for order-api)
- a `PodMonitor` scraping Istio's merged metrics endpoint (§9.6)
- **every scaffolded service**, via `.Files.Glob "services/*.yaml"` (§14.6)

The environment overlay `deploy/env/local/values.yaml` is the **deployment contract**: CI rewrites the
image tags there and commits; [[argo-cd]] syncs. Nothing else writes to it.

## Deployment decisions worth knowing

- **order-api**: `maxSurge: 1, maxUnavailable: 0` — capacity never dips; requires two versions to
  coexist, which forces backwards-compatible changes.
- **order-worker**: `maxSurge: 0, maxUnavailable: 1` — a consumer group rebalances on every membership
  change, so surging causes two rebalances per pod instead of one.
- **`readOnlyRootFilesystem: true`** — if a pod crashes after you set this, that's a finding, not a
  reason to turn it off.

> [!tip] Related
> [[fastapi]], [[go]], [[helm]], [[argo-cd]], [[istio]], [[apache-kafka]], [[floci]], [[paved-paths]]

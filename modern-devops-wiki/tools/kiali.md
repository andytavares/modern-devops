---
type: tool
tags: [service-mesh, observability]
role: the mesh made visible, plus Istio config validation
version: kiali-server 2.30.0
docs: https://kiali.io/docs/
date_added: 2026-08-17
date_updated: 2026-08-17
status: documented-not-observed
---

# Kiali

> [!info] One-liner
> Reads `istio_requests_total` out of [[prometheus]] and draws the mesh. Everything [[istio]] does is otherwise invisible: mTLS either works or it does not, and when it does not the symptom is a 403 in a log somewhere.

## Why it lives in the observability phase

**Without Prometheus there is no graph.** Kiali's topology is derived entirely from
`istio_requests_total`, which it reads out of the Prometheus installed in §13.2. That is why §13.6
documents it next to Prometheus — and why it must be *run* after §9.6, since the merged-metrics scrape
is what puts `istio_requests_total` in Prometheus at all.

## Install

```bash
helm upgrade --install kiali-server kiali/kiali-server \
  --namespace istio-system --version 2.30.0 \
  --set auth.strategy=anonymous \
  --set external_services.prometheus.url=http://monitoring-kube-prometheus-prometheus.monitoring:9090 \
  --set external_services.grafana.enabled=true \
  --set external_services.grafana.internal_url=http://monitoring-grafana.monitoring \
  --set external_services.grafana.external_url=http://grafana.localtest.me
```

Plus `deploy/platform/kiali-ingress.yaml` on `kiali.localtest.me`, port 20001 — an exact host, so
[[ingress-nginx]] routes it directly and it never reaches the Istio gateway (§9.4).

> [!warning] `auth.strategy=anonymous` means anyone who can reach the URL is an admin
> Kiali can **change** Istio configuration from the UI, so on a real cluster this is a
> privilege-escalation path with a web interface. Acceptable here only because the route is
> `localhost` on your laptop. Production is `openid` or `header`; the default is `token`.

## What to actually look at (§13.6)

Generate traffic first — an idle mesh draws an empty graph, which looks identical to a broken install.
Then in **Graph**, select `shop` and `floci` and turn on **Security**:

| What you see | What it means |
|---|---|
| A padlock on `order-api → floci` | mTLS in use on that hop — not configured, *observed* |
| `istio-ingressgateway → order-api` | The edge is meshed and reporting |
| **No edge between order-api and order-worker** | Correct, and worth staring at. [[apache-kafka]] joins them and is outside the mesh. **A service graph is not an architecture diagram** — it shows synchronous calls the proxies saw, and is blind to your entire async path. |
| Red edges into `floci` | §9.5's `deny-all` refusing someone. Click → **Traffic** to see which principal. |

**Istio Config** is the other tab worth your time: it validates every `PeerAuthentication`,
`AuthorizationPolicy` and `DestinationRule` and flags ones referencing workloads or service accounts
that do not exist — the exact failure mode where a typo in `principals` denies everything while
`kubectl get pods` looks perfectly healthy.

## The discipline

**Read-mostly.** Kiali will happily let you edit Istio config through the UI. Do not: every object it
manages is in git, and a console change is one [[argo-cd]] reverts on its next sync — or worse, does
not, because you edited something Argo does not track. Use it to see and to validate; make changes in
the repo. Same argument as [[gitops]].

## Status

Documented, not observed. Kiali is one of the components §14–§16 install that has never been run
against a live cluster in this repo — see [[open-questions]].

## Related

[[istio]] · [[prometheus]] · [[service-mesh]] · [[observability]] · [[grafana]] · [[apache-kafka]]

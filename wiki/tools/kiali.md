---
type: tool
tags: [observability, service-mesh]
role: Makes the mesh visible — traffic graph and Istio config validation
version: kiali-server chart 2.30.0
docs: https://kiali.io/docs/
date_added: 2026-08-15
date_updated: 2026-08-15
status: in-use
---

# Kiali

> [!info] One-liner
> The Istio console: a live traffic graph derived from Prometheus metrics, plus validation of every Istio object in the cluster.

## What it is

A management console for [[istio]]. It reads two things: Istio's configuration from the Kubernetes
API, and traffic metrics from [[prometheus]]. From those it draws a service graph and — the
underrated half — **validates** your Istio objects.

## What it does here

Installed into `istio-system` (§13.6), pointed at our existing Prometheus and Grafana. Exposed at
`kiali.localtest.me`.

**It lives in §13, not §9, for a reason: without Prometheus there is no graph.** The topology is
derived entirely from `istio_requests_total`, which only exists because the PodMonitor scrapes the
merged endpoint (§9.6). Install Kiali before Prometheus and you get an empty page with no error.

What to look for, with the Security display on:

| Observation | Meaning |
|---|---|
| Padlock on `order-api → floci` | mTLS observed in use, not merely configured |
| `ingress-nginx → order-api` present | The edge is enrolled and reporting |
| **No** edge order-api → order-worker | Correct — Kafka joins them, and the mesh cannot see async paths |
| Red edges into `floci` | The default-deny policy refused something; click → Traffic for the principal |

## Key concepts

- **Istio Config tab** validates every `PeerAuthentication`, `AuthorizationPolicy` and
  `DestinationRule`, flagging references to workloads or service accounts that don't exist — exactly
  the failure that otherwise presents as "the app is down" with a healthy `kubectl get pods`.
- **A service graph is not an architecture diagram.** It shows synchronous calls proxies observed. It
  is blind to your entire async path.
- **An idle mesh draws an empty graph**, which looks identical to a broken install. Generate traffic first.

> [!warning] `auth.strategy=anonymous`
> Anyone who reaches the URL is an admin, and Kiali can *change* Istio configuration from the UI — a
> privilege-escalation path with a web interface. Acceptable only because the route is localhost.
> Production: `openid` or `header`. Default is `token`.

Treat it as **read-mostly**: every object it manages is in git, and a change made in the console is
one [[argo-cd]] will revert — or worse, won't, because it isn't tracked.

## Official docs

- Docs: https://kiali.io/docs/
- Installation: https://kiali.io/docs/installation/installation-guide/
- Prometheus/Grafana config: https://kiali.io/docs/configuration/p8s-jaeger-grafana/

> [!tip] Related
> [[istio]], [[prometheus]], [[grafana]], [[service-mesh]], [[observability]]

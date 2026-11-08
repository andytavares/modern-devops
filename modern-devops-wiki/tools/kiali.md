---
type: tool
tags: [service-mesh, observability]
role: the mesh made visible, plus Istio config validation
version: kiali-server 2.30.0
docs: https://kiali.io/docs/
date_added: 2026-08-17
date_updated: 2026-08-23
status: documented-not-observed
---

# Kiali

> [!info] One-liner
> Reads `istio_requests_total` out of [[prometheus]] and draws the mesh. Everything [[istio]] does is otherwise invisible: mTLS either works or it does not, and when it does not the symptom is a 403 in a log somewhere.

## Where it lives, and why it moved (§9.7)

Kiali needs two inputs, and they are created in two different phases:

| Input | Created by | Why Kiali is dead without it |
|---|---|---|
| the `istio-system` namespace | §9.2 (Phase 4) | The chart installs into it, and Helm does not create a namespace without `--create-namespace` |
| `istio_requests_total` in [[prometheus]] | §9.6's ServiceMonitor→PodMonitor swap (Phase 4) | The topology is derived **entirely** from this metric; §13.2's Prometheus is where it is read from, but nothing writes it until the mesh is on and scraped through the sidecar |
| sidecars on the `shop` workloads | §9.3's `rollout restart` (Phase 4) | No proxies, no `istio_requests_total`, no edges |

It used to be **§13.6, in Phase 2**, next to the Prometheus it reads from, with a note saying to read
it there and run it after Phase 4. That was wrong and the human hit it on 2026-08-23:

```
$ helm upgrade --install kiali-server kiali/kiali-server --namespace istio-system --version 2.30.0 ...
Release "kiali-server" does not exist. Installing it now.
Error: create: failed to create: namespaces "istio-system" not found
```

Moved 2026-08-23 to **§9.7**, immediately after §9.6, which is the first point in the build where all
three inputs exist. §9.7→§9.8, §9.8→§9.9, §9.9→§9.10 shifted to make room, and every `§N.M` reference
in `docs/` and this wiki moved with them.

> [!warning] The loud failure is the good one
> Working around the missing namespace with `kubectl create namespace istio-system` makes the chart
> install cleanly against **no control plane**. Kiali then serves an empty graph — visually identical
> to an idle mesh and to a broken install. Nothing in the UI distinguishes the three. Same symptom if
> the `shop` pods were never restarted into the mesh: `1/1` instead of `2/2` and the graph is blank.
> Both are in Appendix B.

The rejected fix is worth recording, because it is the obvious one: keep the section in Phase 2 and
make the deferral louder — a `> [!warning]` at the top of the section plus a back-pointer at the end
of §9.6. **"Read this now, run it later" is not a fix.** It asks the reader to hold a bookmark across
two phases of a document they are executing line by line, and the failure mode of a forgotten bookmark
is the silent one above. Sequencing is the fix; annotation is not. See [[progressive-build]].

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

## What to actually look at (§9.7)

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

Documented, not observed — the graph, the security padlocks and the Istio Config validation above are
all from vendor docs and the tutorial, not from a running instance; see [[open-questions]]. The one
thing that *has* been observed against a live cluster is the install failing at the place the docs
used to put it (2026-08-23, above). See [[progressive-build]] for why `checks/` did not catch it.

> [!warning] One claim in the old §13.6 was wrong and is now fixed
> Its graph table told the reader to look for an `ingress-nginx → order-api` edge and to treat nginx's
> absence as a missing sidecar. **nginx is deliberately not in the mesh** (§9.3 excludes it; the mesh
> boundary is `istio-ingressgateway`), so it never draws an edge and its absence is correct. This page
> already said `istio-ingressgateway → order-api`; the tutorial disagreed with it, and moving the
> section next to §9.3 is what made the contradiction visible. The docs now match this page.

## Related

[[istio]] · [[prometheus]] · [[service-mesh]] · [[observability]] · [[grafana]] · [[apache-kafka]] · [[progressive-build]]

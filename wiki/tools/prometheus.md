---
type: tool
tags: [observability, metrics]
role: Metrics collection, storage and alert evaluation
version: kube-prometheus-stack 82.14.1
docs: https://prometheus.io/docs/introduction/overview/
date_added: 2026-08-15
date_updated: 2026-08-16
status: in-use
---

# Prometheus (via kube-prometheus-stack)

> [!info] One-liner
> A pull-based time-series database that scrapes HTTP endpoints, stores samples, and evaluates alert rules.

## What it is

Prometheus **scrapes** — targets expose `/metrics` and Prometheus fetches on an interval. Combined
with the **Prometheus Operator**, targets are declared as Kubernetes objects (`ServiceMonitor`,
`PodMonitor`, `PrometheusRule`) rather than as scrape config, so monitoring ships with the app.

`kube-prometheus-stack` bundles Prometheus, the Operator, [[grafana]], Alertmanager, node-exporter
and kube-state-metrics in one chart.

## What it does here

Installed into `monitoring` (§13.2), deliberately **not** in the mesh. Our chart ships a `PodMonitor`
scraping [[istio]]'s merged endpoint — see the gotcha below. Alert rules live in
`deploy/platform/alerts.yaml` (§13.5).

> [!warning] The scrape path changed when Istio arrived
> Under STRICT mTLS, a plaintext scrape of `order-api:8000/metrics` is refused, and your dashboards go
> blank with no error except a scrape failure you weren't watching. The fix (§9.6) is to scrape the
> sidecar's **merged endpoint**: `istio-proxy` scrapes the app over loopback inside the pod and
> re-publishes it, combined with Envoy's own metrics, at `/stats/prometheus`. One scrape, both halves,
> survives STRICT. That is why the chart uses a `PodMonitor` and not a `ServiceMonitor`: the endpoint
> is on the pod, not behind a Service.

> [!warning] Two ports, and the wiki previously conflated them — corrected 2026-08-16
> Observed directly on an injected pod (`ingress-nginx-controller`, Istio 1.28):
>
> ```
> istio-proxy container:   name=http-envoy-prom  containerPort=15090
> pod annotations:         prometheus.io/port: 15020
>                          prometheus.io/path: /stats/prometheus
> ```
>
> - **15090** carries the port *name* `http-envoy-prom` and serves **Envoy's own** metrics.
> - **15020** is the **merged** endpoint (pilot-agent: app metrics + Envoy's) and is **unnamed** in the
>   pod spec — it is discoverable only via the `prometheus.io/*` annotations.
>
> This page previously claimed the merged endpoint was *"port 15020 (`http-envoy-prom`)"*, attaching
> the name to the wrong port. The tutorial has it right at §10.1: *"`http-envoy-prom` is the port name
> Istio gives 15090"*. Corrected here in favour of the tutorial **and** the live cluster, which agree.
>
> **The open consequence:** the chart's `PodMonitor` selects `port: http-envoy-prom`, which resolves to
> **15090** — Envoy only. If that is right, §13.3's check that `orders_received_total` is non-zero
> cannot pass, because the application's own metrics live on 15020. Not yet confirmed either way; see
> [[open-questions]]. **Do not change the chart on the strength of this note alone** — it needs a
> meshed `order-api` pod and a real scrape to settle.
>
> Trap: a pod with **no sidecar** has no `http-envoy-prom` port, so the PodMonitor silently matches
> nothing and that workload vanishes from Prometheus. Alert on `absent(...)`.

## Key concepts

- **`serviceMonitorSelectorNilUsesHelmValues: false`** (and the PodMonitor/rule equivalents) is the
  single most useful line in the values file: with the default, Prometheus only discovers monitors
  labelled `release: monitoring`, and third-party monitors are ignored **with no error anywhere**.
- **Alert on symptoms, not causes** (§13.5). One alert on "orders in, nothing out" covers a dozen root
  causes; "worker pod restarted" fires during every normal deploy and trains people to ignore the pager.
- **`for:` is not padding.** It requires the condition to hold continuously — without it a 20-second
  blip during a rolling deploy pages someone at 3am.

## The CRDs arrive late, and that is an ordering constraint

`kube-prometheus-stack` installs the `monitoring.coreos.com` CRDs in §13.2 — **two sections after**
[[argo-cd]] starts syncing `order-platform` in §11.4. Any `PodMonitor` or `ServiceMonitor` shipped in
a chart before that point cannot render.

> [!warning] Hit 2026-08-16
> `order-platform` shipped `podMonitor.enabled: true` by default. Argo CD does not skip a resource
> whose CRD is missing — it fails the **entire** Application sync, so `order-api`, `order-worker`,
> both Services, both ServiceAccounts and the Ingress all sat `Missing` while `kubectl -n shop get
> pods` returned nothing. §11.4 through §12.6 were unreachable.
>
> Fix: default `podMonitor.enabled: false` in the **chart's** `values.yaml` and flip it in §13.3 once
> the CRDs exist. Not in `deploy/env/local/values.yaml` — [[buildkite]] rewrites that overlay
> wholesale on every deploy, so anything else placed there is lost on the next green build. See
> [[argo-cd]].

## Official docs

- Overview: https://prometheus.io/docs/introduction/overview/
- Querying (PromQL): https://prometheus.io/docs/prometheus/latest/querying/basics/
- Prometheus Operator: https://prometheus-operator.dev/docs/getting-started/introduction/
- kube-prometheus-stack chart: https://github.com/prometheus-community/helm-charts/tree/main/charts/kube-prometheus-stack
- Istio's Prometheus integration: https://istio.io/latest/docs/ops/integrations/prometheus/

> [!tip] Related
> [[grafana]], [[istio]], [[kiali]], [[observability]], [[kubernetes]]

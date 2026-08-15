---
type: tool
tags: [observability, metrics]
role: Metrics collection, storage and alert evaluation
version: kube-prometheus-stack 82.14.1
docs: https://prometheus.io/docs/introduction/overview/
date_added: 2026-08-15
date_updated: 2026-08-15
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
> re-publishes it, combined with Envoy's own metrics, on port **15020** (`http-envoy-prom`, path
> `/stats/prometheus`). One scrape, both halves, survives STRICT. That is why the chart uses a
> `PodMonitor` and not a `ServiceMonitor`: the merged endpoint is on the pod, not behind a Service.
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

## Official docs

- Overview: https://prometheus.io/docs/introduction/overview/
- Querying (PromQL): https://prometheus.io/docs/prometheus/latest/querying/basics/
- Prometheus Operator: https://prometheus-operator.dev/docs/getting-started/introduction/
- kube-prometheus-stack chart: https://github.com/prometheus-community/helm-charts/tree/main/charts/kube-prometheus-stack
- Istio's Prometheus integration: https://istio.io/latest/docs/ops/integrations/prometheus/

> [!tip] Related
> [[grafana]], [[istio]], [[kiali]], [[observability]], [[kubernetes]]

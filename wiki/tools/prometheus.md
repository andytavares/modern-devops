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
> **The consequence, settled 2026-08-16:** the chart's `PodMonitor` selected `port: http-envoy-prom`
> — 15090, Envoy only — so `orders_received_total` would never have appeared and §13.3's first check
> could not pass. `istio_requests_total` *is* on 15090, so [[kiali]] would have looked healthy the
> whole time: a silent half-failure. **Fixed to `portNumber: 15020`.**

## Scrape the sidecar on 15020, addressed by number

| Port | Named in pod spec | Serves |
|---|---|---|
| 15090 | `http-envoy-prom` | `envoy_*` and `istio_requests_total` — **Envoy only** |
| 15020 | *(unnamed)* | the above **plus** `istio_agent_*` and the **merged application metrics** |

Istio's docs settle it: *"forwards requests to the sidecar telemetry port **15020 for merged metrics**
or **15090 for Envoy-only metrics**"* ([secure metrics](https://istio.io/latest/docs/tasks/observability/metrics/secure-metrics)),
and the `enablePrometheusMerge` mesh setting is what makes the agent merge app metrics onto 15020 in
the first place.

Because 15020 has **no name** in the pod spec, a `PodMonitor` cannot reach it with `port:`. Use
`portNumber: 15020` — `targetPort` exists but the CRD marks it *"Deprecated: use 'port' or
'portNumber' instead"*.

```yaml
podMetricsEndpoints:
  - portNumber: 15020
    path: /stats/prometheus
```

Verified against a live sidecar (counts of metric lines) and accepted by
`kubectl apply --dry-run=server` against the installed CRD.
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

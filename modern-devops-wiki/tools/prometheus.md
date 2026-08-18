---
type: tool
tags: [observability, monitoring]
role: scraping, storage, alert evaluation
version: kube-prometheus-stack 88.3.0 (Prometheus Operator v0.93.0)
docs: https://prometheus.io/docs/
date_added: 2026-08-17
date_updated: 2026-08-17
status: in-use
---

# Prometheus

> [!info] One-liner
> Installed as `kube-prometheus-stack`, which is Prometheus, Alertmanager, [[grafana]], node-exporter, kube-state-metrics and the Operator in one chart. The Operator is the part that matters.

## Why the Operator is the point (§13.1)

It introduces `ServiceMonitor`, `PodMonitor` and `PrometheusRule` CRDs, so **applications declare their
own scrape config and alerts in their own charts**. No central `prometheus.yml` every team has to send
a PR against. That is [[reconciliation]] applied to monitoring config.

## `infra/monitoring-values.yaml`, three lines that matter

**`serviceMonitorSelectorNilUsesHelmValues: false`** (and the `podMonitor`/`rule` equivalents) is the
single most useful line in the file. With the default (`true`), Prometheus only picks up monitors
labelled `release: monitoring` — our chart sets it deliberately, but any chart that does not is
**silently ignored, with no error anywhere.** Trades a little namespace hygiene for monitors that get
discovered whoever shipped them.

**`sidecar.dashboards.searchNamespace: ALL`** with `label: grafana_dashboard` — how app teams ship
dashboards with their app rather than via a ticket. See [[grafana]].

**`kubeControllerManager`/`kubeScheduler`/`kubeEtcd`/`kubeProxy: enabled: false`** — those control-plane
endpoints are not individually addressable on [[kind]] the way a managed cluster exposes them.

## The monitor swap, which is the most instructive thing in this platform

Exactly one of the chart's two monitors should ever be on. Turning both on double-scrapes every target
and doubles your counters.

| Phase | Monitor | Scrapes | Why it stops working |
|---|---|---|---|
| §13.3 (pre-mesh) | `ServiceMonitor` | Service port name, plaintext | STRICT [[mtls]] refuses it |
| §9.6 (post-mesh) | `PodMonitor` | `portNumber: 15020`, `/stats/prometheus` | — |

§9.6 is the lesson: STRICT mTLS means every connection into a meshed pod must present a client
certificate. Prometheus has no sidecar and no certificate, so its scrape is refused **at the proxy**.
Nothing logs an error. Nothing restarts. `kubectl get pods` says `2/2`. **A security control that
silently breaks observability is the ordinary case, not a freak event** — and in production it arrives
as "the dashboard has been flat since Tuesday and nobody noticed".

The fix is to scrape the sidecar's **merged endpoint**: `istio-proxy` scrapes the app over loopback
*inside* the pod, where there is no mTLS to satisfy, and republishes those metrics combined with
Envoy's own. One scrape, both halves.

> [!warning] It must be 15020, and it must be addressed by **number**
> Istio's docs: *"forwards requests to the sidecar telemetry port **15020 for merged metrics** or
> **15090 for Envoy-only metrics**"*. 15090 is the port carrying the **name** `http-envoy-prom`; 15020
> is **unnamed** in the pod spec, so `port:` cannot reach it and `portNumber: 15020` is required
> (`targetPort` is deprecated in favour of `portNumber`).
>
> Selecting `http-envoy-prom` by name gets you `istio_requests_total` — so [[kiali]] looks perfectly
> healthy — while the application's own `orders_received_total` **never appears again.** A half-failure
> that looks like a success is worse than an outage. This defect was live in this repo and is fixed;
> §13.3's first verification step could not have passed with it.

> [!warning] The `PodMonitor` trap that has no error at all
> A pod with **no sidecar** has no merged endpoint, so the monitor silently matches nothing and that
> workload vanishes from Prometheus. **A workload that leaves the mesh loses its metrics.** Worth an
> alert of its own: `absent(up{job="order-platform"})`.

Verify you get both halves from one scrape:

```bash
curl -s 'http://localhost:9090/api/v1/query?query=orders_received_total' | jq '.data.result | length'
curl -s 'http://localhost:9090/api/v1/query?query=istio_requests_total'  | jq '.data.result | length'
```

Both non-zero. Istio's empty but yours not → you are on the application port. Yours empty but Istio's
not → you are on 15090.

## The alerts (`deploy/platform/alerts.yaml`)

`OrderPipelineStalled` (critical, `for: 5m`), `OrderIngestErrorRate` (>5%, `for: 10m`),
`OrderEventAgeHigh` (>120s, `for: 5m`).

**Alert on symptoms, not causes.** `OrderPipelineStalled` fires when the business outcome fails —
orders in, nothing out — regardless of why. One alert covers a dozen root causes. "Worker pod
restarted" fires constantly during normal deploys and trains people to ignore the pager. **Every alert
should be something a human must act on right now; if it is not, it is a dashboard panel.**

**`for:` is not padding.** Without it a 20-second blip during a rolling deploy pages someone at 3am.
Tune it against your actual deploy duration.

## Related

[[grafana]] · [[observability]] · [[istio]] · [[kiali]] · [[order-platform]] · [[port-naming]] · [[reconciliation]]

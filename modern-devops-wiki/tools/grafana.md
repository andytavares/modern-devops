---
type: tool
tags: [observability, dashboards]
role: dashboards as code
version: bundled in kube-prometheus-stack 88.3.0
docs: https://grafana.com/docs/grafana/latest/
date_added: 2026-08-17
date_updated: 2026-08-17
status: documented-not-observed
---

# Grafana

> [!info] One-liner
> The read side of [[prometheus]]. The only thing worth knowing about it here is that dashboards are ConfigMaps, not clicks.

## Dashboards as code

The kube-prometheus-stack sidecar imports **any ConfigMap in any namespace** carrying
`grafana_dashboard: "1"`, because `infra/monitoring-values.yaml` sets
`sidecar.dashboards.searchNamespace: ALL`. That is how app teams ship dashboards with their app rather
than via a ticket.

`deploy/platform/grafana-dashboard.yaml` is the Order Platform dashboard: orders accepted/sec, orders
persisted/sec, ingest latency p50/p95/p99, pipeline lag (`max(order_event_age_seconds)`), and
unprocessed (`accepted - persisted`).

Dashboards clicked together in the UI are lost when the pod restarts. Both halves of the selector must
match or nothing appears: the label must be exactly `grafana_dashboard: "1"` and
`searchNamespace: ALL` must be set (Appendix B).

## Percentiles come from histograms, not averages (§13.4)

`rate(x_sum[5m]) / rate(x_count[5m])` gives you a **mean**, and the mean latency of a bimodal system is
a number that describes no request that ever happened. `histogram_quantile` over `_bucket` is the
correct instrument.

The catch: **bucket boundaries are fixed at instrumentation time**, so a p99 landing in your top bucket
reads as that bucket's upper bound. Check `prometheus.DefBuckets` covers your real range — order-worker
uses exactly those defaults.

## Access

`http://grafana.localtest.me`, `admin` / `admin`, via an exact-host [[ingress-nginx]] Ingress so it
never routes through the Istio gateway. [[kiali]] is configured to link into it
(`external_services.grafana.external_url`).

## Status

Documented, not observed — part of the §14–§16 block that has never run against a live cluster in this
repo. See [[open-questions]].

## Related

[[prometheus]] · [[observability]] · [[kiali]] · [[go]] · [[fastapi]]

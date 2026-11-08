---
type: concept
tags: [monitoring, operations]
date_added: 2026-08-17
date_updated: 2026-08-17
---

# Observability

> [!info] One-liner
> Metrics only — you can see *that* it broke, not *why*. Knowing exactly where that line sits is the point of this page.

## Why it comes before delivery automation

**The moment you can deploy quickly is the moment you need to know quickly whether the deploy was
fine.** Phase 2 sits before Phase 3 for that reason and no other (§13, §11 intro).

And before the mesh, so that when [[istio]] breaks the scrape it happens *to something you built and
understand*, with the fix in front of you. Doing the mesh first turns the same lesson into a footnote
you skim.

## What exists

**Application metrics.** order-api: `orders_received_total{result}`,
`order_ingest_duration_seconds`, `pricing_calls_total{result,served_by}`. order-worker:
`orders_processed_total{result}`, `order_process_duration_seconds`, `order_event_age_seconds`.

**Mesh metrics**, free once the merged scrape works: `istio_requests_total` and friends, which is what
[[kiali]] draws from.

**Kubernetes metrics** from kube-state-metrics and node-exporter, via kube-prometheus-stack.

> `served_by` is safe as a metric label **only because its cardinality is bounded by the number of
> deployed pricing versions.** Do not label metrics with anything a caller controls.

## The interaction that is the whole lesson (§9.6)

STRICT [[mtls]] refuses [[prometheus]]' plaintext scrape at the proxy. **Nothing logs an error. Nothing
restarts. `kubectl get pods` says `2/2`.** Your dashboards draw flat lines.

> **A security control that silently breaks observability is the ordinary case, not a freak event.** In
> production it arrives as "the dashboard has been flat since Tuesday and nobody noticed."

The fix — scraping the sidecar's merged endpoint on `portNumber: 15020` — and the half-failure that
looks like a success (selecting 15090 by name, so Kiali works while your own metrics never appear) are
on [[prometheus]].

## Alert on symptoms, not causes

`OrderPipelineStalled` fires when the business outcome fails — orders in, nothing out — regardless of
*why*: worker crashed, Kafka unreachable, DynamoDB rejecting, consumer group stuck. **One alert covers
a dozen root causes.** Alerts like "worker pod restarted" fire constantly during normal deploys and
train people to ignore the pager.

> **Every alert should be something a human must act on right now. If it is not, it is a dashboard
> panel.**

The `for:` clause is part of the alert, not padding: without it a 20-second blip during a rolling
deploy pages someone at 3am. Tune it against your actual deploy duration.

## The monitoring-stopped alert nobody writes

A pod with no sidecar has no merged endpoint, so the `PodMonitor` matches nothing and that workload
**vanishes from Prometheus with no error at all.** `absent(up{job="order-platform"})` is the alert for
it, and it is precisely the class §13.5 argues you should page on. Same shape as a `ServiceMonitor`
selecting a port name that no longer exists after a rename — see [[port-naming]].

## The honest gaps

**No logs, no traces.** Appendix C: Loki for logs, Tempo + OpenTelemetry for traces, and [[grafana]]
already fronts all three. Envoy can emit a span for every hop and this platform collects none of them —
Istio needs only `meshConfig.defaultConfig.tracing` pointed at a collector, and Kiali would then link
graph edges to traces.

**No consumer-group lag scraped.** `order_event_age_seconds` is the in-band proxy this platform alerts
on instead; real lag needs the [[strimzi]] CLI.

**Percentiles need histograms, not averages** — and bucket boundaries are fixed at instrumentation
time, so a p99 in your top bucket reads as that bucket's upper bound. See [[grafana]].

## Related

[[prometheus]] · [[grafana]] · [[kiali]] · [[istio]] · [[mtls]] · [[service-mesh]] · [[port-naming]] · [[health-checks]]

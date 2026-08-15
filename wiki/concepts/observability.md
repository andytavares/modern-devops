---
type: concept
tags: [observability, operations]
docs: https://prometheus.io/docs/practices/naming/
date_added: 2026-08-15
date_updated: 2026-08-15
---

# Observability in this platform

> [!info] One-liner
> Metrics only, so far: you can see *that* something broke, rarely *why*. Logs and traces are the known gap.

## What exists

| Layer | Tool | Notes |
|---|---|---|
| Collection | [[prometheus]] | pull-based; targets declared as `PodMonitor`/`ServiceMonitor` CRDs |
| Dashboards | [[grafana]] | shipped as code, as ConfigMaps labelled `grafana_dashboard: "1"` |
| Alerting | Alertmanager | rules in `deploy/platform/alerts.yaml` |
| Mesh view | [[kiali]] | traffic graph from `istio_requests_total`, plus Istio config validation |

## The two rules worth keeping

- **Alert on symptoms, not causes.** `OrderPipelineStalled` — orders in, nothing out — covers a dozen
  root causes with one alert. "Worker pod restarted" fires during every normal deploy and trains
  people to ignore the pager. **Every alert should require a human to act now**; if it doesn't, it's a
  dashboard panel.
- **`for:` is load-bearing.** The condition must hold continuously, or a 20-second blip during a
  rolling deploy pages someone at 3am. Tune it against your actual deploy duration.

## The Istio interaction, which is the subtle part

Turning on STRICT mTLS breaks plaintext scrapes and your dashboards go blank with no error except a
scrape failure nobody was watching (§9.6). Three answers, ranked:

1. Put Prometheus in the mesh — works, but injects sidecars into the tooling you'd use to debug the
   mesh, and node-exporter's host networking needs its own opt-out.
2. Exempt the metrics port with `portLevelMtls` — fine when metrics have a dedicated port, useless
   when the app serves `/metrics` on its traffic port.
3. **Scrape the sidecar's merged endpoint on 15020** — one scrape, app + Envoy metrics, survives
   STRICT. This is what we do.

## The gaps

- **No logs pipeline** (Loki) and **no traces** (Tempo + OpenTelemetry). Grafana already fronts both.
  Istio can emit a span per hop with one `meshConfig` setting — the cheapest tracing you'll ever get.
- No SLOs, no error budgets. Alerts are thresholds, not objectives.

## Official docs

- Metric naming: https://prometheus.io/docs/practices/naming/
- Alerting practices: https://prometheus.io/docs/practices/alerting/
- Istio Prometheus integration: https://istio.io/latest/docs/ops/integrations/prometheus/

> [!tip] Related
> [[prometheus]], [[grafana]], [[kiali]], [[istio]], [[service-mesh]]

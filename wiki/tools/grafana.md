---
type: tool
tags: [observability, dashboards]
role: Dashboards and the query front-end for metrics
version: bundled in kube-prometheus-stack 82.14.1
docs: https://grafana.com/docs/grafana/latest/
date_added: 2026-08-15
date_updated: 2026-08-15
status: in-use
---

# Grafana

> [!info] One-liner
> The query and visualisation layer — and, in this stack, the eventual single pane over metrics, logs and traces.

## What it does here

Bundled with kube-prometheus-stack, exposed at `grafana.localtest.me` (§13.2). The Order Platform
dashboard is shipped **as code**: a ConfigMap labelled `grafana_dashboard: "1"`, discovered by
Grafana's sidecar with `sidecar.dashboards.searchNamespace: ALL` (§13.4).

That labelling convention is the whole point: **app teams ship dashboards with their app**, in the
same PR as the code, rather than filing a ticket. A dashboard clicked together in the UI is lost when
the pod restarts.

## Key concepts

- **Datasource + panel + query.** The panels are thin; the PromQL is where the meaning is.
- **Dashboards as ConfigMaps** — the label and the `searchNamespace` setting must both be right, and
  when a dashboard doesn't appear it is almost always one of those two (Appendix B).
- Grafana also fronts **Loki** (logs) and **Tempo** (traces) — both listed as gaps here, and both
  worth adding before you need them rather than during an incident.
- [[kiali]] links its graph out to Grafana dashboards when `external_services.grafana` is configured.

## Official docs

- Docs: https://grafana.com/docs/grafana/latest/
- Provisioning dashboards: https://grafana.com/docs/grafana/latest/administration/provisioning/
- Dashboard JSON model: https://grafana.com/docs/grafana/latest/dashboards/build-dashboards/view-dashboard-json-model/

> [!tip] Related
> [[prometheus]], [[kiali]], [[observability]]

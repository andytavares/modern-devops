---
type: tool
tags: [packaging, kubernetes]
role: Packaging — our chart, and how we install everything third-party
version: ">= 3.8.0 (OCI registry support required)"
docs: https://helm.sh/docs/
date_added: 2026-08-15
date_updated: 2026-08-15
status: in-use
---

# Helm

> [!info] One-liner
> Go templates that render Kubernetes YAML, packaged as a versioned, distributable unit.

## What it is

A templating and release-management tool. A **chart** is a directory of templates plus a
`values.yaml` of defaults; `helm install/upgrade` renders it and applies the result, recording a
release history in-cluster so `helm rollback` works.

The part people underrate: it is the de facto *distribution* format. Almost every third-party
component here — [[openbao]], [[external-secrets-operator]], [[strimzi]], [[istio]], [[kiali]],
[[backstage]], kube-prometheus-stack — ships as a chart, so knowing Helm is not optional even if you
template your own manifests some other way.

## What it does here

Two distinct jobs, worth keeping separate in your head:

1. **Installing other people's software** — one `helm upgrade --install` per platform component,
   pinned to an explicit `--version`.
2. **Packaging ours** — `deploy/charts/order-platform` renders order-api and order-worker (§10.1),
   plus every scaffolded service via `.Files.Glob "services/*.yaml"` (§14.6). Rendered by
   [[argo-cd]], never by a human in CI.

Values layering: chart defaults → `deploy/env/local/values.yaml` (the environment overlay, which CI
rewrites with image tags). Nothing else writes to the overlay.

## Key concepts

- **`.Files.Glob`** reads files inside the chart directory. It is what turns onboarding a service from
  an *edit* of a shared values file into a *creation* of a new file — conflict-free and trivially
  reviewable (§14.6).
- **`helm template`** renders locally with no cluster. Do it before every commit (§10.3).
- **Release history lives in the cluster**, in Secrets. If you delete the namespace, you delete the
  rollback history.

## Why this, not the alternative

vs **Kustomize** (§10.4): Kustomize overlays strategic-merge patches onto real YAML you can read
without rendering — simpler and more auditable when your only variance is image tags and replica
counts. Helm wins here for one reason: a single parameter CI can mechanically rewrite, with the rest
derived from it, plus the fact that third-party software already ships as charts. If you own all the
manifests and your variance is small, Kustomize is the better tool.

## Gotchas

- Template logic becomes an unreadable program fast. Three levels of `{{- if }}` is a smell.
- `helm upgrade` with only a value change won't restart pods — hence the `checksum/config` annotation
  pattern in the chart (§10.1).
- Values deep-merge; a map in the overlay does not replace the chart's map, it merges into it.

## Official docs

- Docs: https://helm.sh/docs/
- Chart template guide: https://helm.sh/docs/chart_template_guide/
- Built-in objects (`.Files`, `.Release`, `.Chart`): https://helm.sh/docs/chart_template_guide/builtin_objects/

> [!tip] Related
> [[kubernetes]], [[argo-cd]], [[gitops]], [[paved-paths]]

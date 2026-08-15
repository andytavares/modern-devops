---
type: tool
tags: [cd, gitops]
role: Continuous delivery — the cluster pulls from git
version: v3.4.7
docs: https://argo-cd.readthedocs.io/en/stable/
date_added: 2026-08-15
date_updated: 2026-08-15
status: in-use
---

# Argo CD

> [!info] One-liner
> A controller that continuously reconciles the cluster against a git repo — CI never needs cluster credentials.

## What it is

A GitOps engine. An **`Application`** names a repo, a path, a revision and a destination; the
controller renders it (Helm, Kustomize or plain YAML) and applies it, then keeps applying it. Drift
is detected and, with `selfHeal`, reverted.

The security consequence is the headline: **delivery is a pull, not a push.** CI's total privilege
becomes "push a commit". If CI is compromised, the attacker gets a reviewable, revertible commit —
not cluster admin. Compare `helm upgrade` running in a pipeline with a kubeconfig.

## What it does here

App-of-apps (§11.4): a root `Application` points at `deploy/argocd/apps/`, which declares:

| Application | Path | Sync policy |
|---|---|---|
| `order-platform` | `deploy/charts/order-platform` + `env/local/values.yaml` | `prune: true`, `selfHeal: true` |
| `platform` | `deploy/platform` (recursive) | `prune: false`, `selfHeal: true` |

The `platform` app recursing `deploy/platform` is what makes the [[backstage]] infrastructure paved
path work with no extra wiring — a new manifest in a subdirectory is picked up automatically (§14.7).

## Key concepts

- **`prune` is per-Application and deliberate** (§11.4). `true` on workloads makes git authoritative;
  `false` on shared platform infra, because a bad rebase that drops a file should not delete your
  Kafka cluster and its PVCs. Different blast radius, different setting.
- **`selfHeal: true` makes `kubectl edit` temporary.** Correct default, infuriating during an
  incident. Escape hatch: `argocd app set <app> --sync-policy none`, consciously.
- **Polling is a fallback, not the design.** Default 3-minute interval; the production answer is a
  webhook to `argocd-server/api/webhook`, which needs an inbound URL a laptop doesn't have.
- `Degraded` on a nonexistent image tag is Argo faithfully reporting that desired state is
  unachievable — not a bug.

## Gotchas

- Argo would otherwise try to own the Ingress it is served from; the tutorial excludes
  `argocd-ingress.yaml` to avoid a self-referential sync.
- The initial admin secret is a static credential with no expiry — delete it after changing the password.

## Official docs

- Docs: https://argo-cd.readthedocs.io/en/stable/
- Application spec: https://argo-cd.readthedocs.io/en/stable/operator-manual/application.yaml
- App-of-apps pattern: https://argo-cd.readthedocs.io/en/stable/operator-manual/cluster-bootstrapping/

> [!tip] Related
> [[gitops]], [[helm]], [[buildkite]], [[immutable-image-tags]], [[backstage]]

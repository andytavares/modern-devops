---
type: concept
tags: [delivery, operations]
docs: https://opengitops.dev/
date_added: 2026-08-15
date_updated: 2026-08-15
---

# GitOps

> [!info] One-liner
> Git holds desired state; a controller in the cluster continuously makes reality match. Delivery is a pull, not a push.

## The four principles

Per OpenGitOps: desired state is **declarative**, **versioned and immutable**, **pulled automatically**,
and **continuously reconciled**. The fourth is the one people skip and the one that matters — a
one-shot `kubectl apply` from CI is not GitOps, it is a deployment script with extra steps.

## Why it's the security story, not just the workflow

Push-based CD means CI holds cluster credentials. Pull-based means CI's total privilege is *push a
commit* — reviewable, revertible, and worthless to an attacker who wants cluster admin. In this
project ([[argo-cd]], §11.1) CI has no kubeconfig, no cluster token, and no `helm` binary.

## How it shows up here

- [[argo-cd]] reconciles `deploy/` continuously, with `selfHeal: true` (so `kubectl edit` is temporary).
- [[buildkite]] ends its pipeline by **writing an image tag into git**, and stops.
- [[backstage]]'s paved paths produce **pull requests**, so even provisioning infrastructure is a
  reviewed commit (§14.7).

## The tensions, stated honestly

- **Secrets can't live in git.** That gap is what [[external-secrets-operator]] fills.
- **`prune` is a blast-radius decision**, not a default. `true` on workloads makes git authoritative;
  `false` on shared infra, because a bad rebase should not delete a Kafka cluster and its PVCs.
- **Mono-repo means CI commits to the repo CI builds from**, which creates a deploy→build→deploy loop
  that needs an explicit guard (§12.5). Split repos don't have this problem — the strongest practical
  argument for splitting.
- **Polling is a fallback.** The real fix for latency is a webhook, not a shorter interval.

## Official docs

- OpenGitOps principles: https://opengitops.dev/
- Argo CD: https://argo-cd.readthedocs.io/en/stable/

> [!tip] Related
> [[argo-cd]], [[buildkite]], [[immutable-image-tags]], [[secrets-management]], [[paved-paths]]

---
type: concept
tags: [delivery, operations, security]
docs: https://opengitops.dev/
date_added: 2026-08-17
date_updated: 2026-08-17
---

# GitOps

> [!info] One-liner
> Git holds desired state; a controller in the cluster continuously makes reality match. Delivery is a pull, not a push.

## The four principles

Per OpenGitOps: desired state is **declarative**, **versioned and immutable**, **pulled
automatically**, and **continuously reconciled**. The fourth is the one people skip and the one that
matters — a one-shot `kubectl apply` from CI is not GitOps, it is a deployment script with extra steps.
See [[reconciliation]].

## It is the security story, not just the workflow

Push-based CD means CI holds cluster credentials. Your build system is internet-facing and runs
arbitrary code from pull requests; giving it production credentials is how a supply-chain compromise
becomes a production compromise.

Pull-based means **[[buildkite]]'s total privilege is: push a commit to one repo.** No kubeconfig, no
cluster token, no `helm` binary in the deploy step. Compromise the pipeline and the attacker gets a
reviewable, revertible commit.

## What it costs, stated honestly

**Deploys become asynchronous.** CI finishes with "commit pushed", not "deployed". You need
[[argo-cd]]'s UI or CLI to answer "is it live yet?", and a failed deploy surfaces in a different tool
than the build that caused it. Teams that dislike GitOps almost always dislike exactly this (§11.1).

**Latency is real.** Polling is 3 minutes by default, and the production fix is a webhook, not a
shorter interval.

**Two owners for one object is a fight nobody wins.** §11.4 makes you `helm uninstall` the release you
installed by hand before Argo takes over. If Argo cannot recreate it from the repo, the repo was never
a truthful description of your platform.

## The handoff at the seam

CI's *entire* interface to CD is one file: `deploy/env/local/values.yaml`, rewritten wholesale and
committed with `chore(deploy): order-platform <sha> [skip ci]`. Narrow, reviewable, revertible.

Two consequences follow, and both are covered elsewhere: the [[dynamic-pipelines]] loop guard exists
because CI commits into the repo it builds from, and every service the chart deploys must have a tag in
that file or it silently falls back to an image nobody built ([[order-platform]]).

## Rollback is a git operation

`git revert` the deploy commit and push — the audit trail records who and when. `argocd app rollback`
is faster in an incident and puts the cluster out of sync with git until you follow up with the revert.
**Know which one you are doing** (§15.4).

## The rule that keeps it true

Every object [[kiali]] can edit, every namespace label, every Istio policy is in git. A change made in
a console is one Argo reverts on its next sync — **or worse, does not, because you edited something
Argo does not track.** The same argument makes `istio-injection: enabled` a manifest field rather than
a `kubectl label` (§9.3).

## Related

[[argo-cd]] · [[reconciliation]] · [[buildkite]] · [[immutable-image-tags]] · [[dynamic-pipelines]] · [[order-platform]] · [[kiali]]

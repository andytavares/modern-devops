---
type: concept
tags: [delivery, ci]
docs: https://kubernetes.io/docs/concepts/containers/images/
date_added: 2026-08-15
date_updated: 2026-08-15
---

# Immutable image tags

> [!info] One-liner
> Tag images with the commit SHA, never `latest` — so "what is running" and "what is in git" are the same question.

## The problem with `latest`

It is a mutable pointer. Two clusters can run different code while both claim to run `latest`.
Rollback is undefined, because there is no earlier thing to roll back *to*. And a pod restart can
silently change the code you're running.

## What we do

[[buildkite]] tags every image with the 12-character commit SHA and writes that tag into
`deploy/env/local/values.yaml`, which [[argo-cd]] renders (§12.5). `latest` is also pushed, purely as
a convenience pointer for humans — **nothing in the deployment path reads it.**

The consequence worth noticing: the deploy step's total privilege is "push a commit". CI has no
cluster credentials at all. See [[gitops]].

## Related discipline

- **`imagePullPolicy: IfNotPresent`** is safe precisely *because* tags are immutable. With `latest` you
  need `Always`, and now every pod start depends on registry availability.
- **Stamp the version into the binary** too (`-ldflags "-X main.version=$SHA"`), so a running process
  can report which commit it is.
- Digest pinning (`@sha256:...`) is strictly stronger than SHA tags; the tradeoff is legibility.

> [!tip] Related
> [[buildkite]], [[argo-cd]], [[gitops]], [[go]], [[dynamic-pipelines]]

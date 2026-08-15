---
type: concept
tags: [security, secrets]
docs: https://external-secrets.io/latest/
date_added: 2026-08-15
date_updated: 2026-08-15
---

# Secrets management

> [!info] One-liner
> Git holds a *reference*; the value lives in a secret manager and is synced into Kubernetes by a controller.

## Why Kubernetes Secrets alone aren't enough

A Kubernetes Secret is **base64 — encoding, not encryption**. It cannot be committed to git, which
puts a hole in [[gitops]]: everything is declarative except the one thing you most need to be.

## The pattern

[[openbao]] holds values → [[external-secrets-operator]] authenticates as a ServiceAccount, reads
them, and writes Kubernetes Secrets → workloads consume them as env vars or files. Git contains only
`ExternalSecret` manifests naming *which* secret to fetch.

## The three timing facts that catch people

1. **`refreshInterval` is a poll.** The Secret updates on ESO's schedule, not instantly.
2. **Running pods keep the old value.** Env vars are set at container start. Rotation is
   update → resync → **restart** (§15.4 ⑤). Measure your real rotation window; don't assume it.
3. **Bootstrap always has one manual seed.** Buildkite must be able to clone before it can run the
   pipeline that would create its own credentials. The discipline is keeping it to *one*.

## Scoping, which is where the real security is

- Fine-grained PATs, scoped to **one repository**, never an org.
- Separate tokens for separate consumers ([[buildkite]] and [[backstage]] get their own) so blast
  radius and rotation are independent.
- Revoking credentials is part of teardown, not an afterthought.

> [!tip] Related
> [[openbao]], [[external-secrets-operator]], [[gitops]], [[mtls]], [[backstage]]

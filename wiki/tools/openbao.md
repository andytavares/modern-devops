---
type: tool
tags: [secrets, security]
role: The source of truth for every secret
version: chart 0.29.1 (OpenBao 2.5.0)
docs: https://openbao.org/docs/
date_added: 2026-08-15
date_updated: 2026-08-15
status: in-use
---

# OpenBao

> [!info] One-liner
> The Linux Foundation fork of HashiCorp Vault from its last MPL version — API-compatible, open governance.

## What it is

A secrets manager: encrypted storage, dynamic secrets, leases, audit logging, and pluggable auth
methods. OpenBao forked Vault after HashiCorp moved Vault to the BUSL licence in 2023. It is
**API-compatible**, so paths, policies, the KV v2 engine and Kubernetes auth all transfer to Vault
verbatim — including the ecosystem: [[external-secrets-operator]] talks to it using its **`vault`
provider**, and expecting an `openbao` provider key is the single most common mistake here (§7.5).

## What it does here

Holds every secret the platform needs (§7.3), under a **KV v2** mount named `shop`:

| Path | Contents |
|---|---|
| `shop/order-api` | `signing_key` — the HMAC key order-api signs with |
| `shop/nexus` | registry username/password, for image pulls and CI pushes |
| `shop/backstage` | the portal's GitHub PAT |

Kubernetes auth (§7.4) lets [[external-secrets-operator]] authenticate as a ServiceAccount rather
than holding a static token.

## Key concepts

- **KV v2 stores data under `<mount>/data/<path>`** and metadata under `<mount>/metadata/<path>`.
  A policy written as `path "shop/*"` will fail; it must be `path "shop/data/*"`. Forgetting the
  `/data/` segment is the second most common mistake in the whole tutorial.
- **v2 gives versioning and soft-delete**; v1 is a flat overwrite with no history. Always v2.
- **Kubernetes auth needs TokenReview**, so OpenBao's ServiceAccount needs the `system:auth-delegator`
  ClusterRole binding.
- The tutorial runs it **unsealed with a root token in dev mode**. Production means Raft storage,
  auto-unseal via a KMS, and no root token in anyone's shell history.

## Official docs

- Docs: https://openbao.org/docs/
- Helm on Kubernetes: https://openbao.org/docs/platform/k8s/helm/run/
- Kubernetes auth: https://openbao.org/docs/auth/kubernetes/

> [!tip] Related
> [[external-secrets-operator]], [[secrets-management]], [[kubernetes]], [[backstage]]

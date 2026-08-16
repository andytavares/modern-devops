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

## Why this, not the alternative

**vs HashiCorp Vault** — a licence-and-cost substitution made deliberately, per the enterprise-shaping
principle stated in §0 and argued in §7.1.

**What you get at work is Vault**, most likely Vault Enterprise: quote-only, routinely a five- or
six-figure annual contract. Vault also moved to the BUSL in 2023, so it is not open source in any sense
a public tutorial can rely on.

**Why OpenBao teaches the same thing.** It is API-compatible, and the list is concrete: paths, ACL
policy documents, the KV v2 engine with its `/data/` and `/metadata/` split, the Kubernetes auth method
and its TokenReview dependency, tokens and leases, and the CLI verbs. The strongest proof is
ecosystem-level rather than a claim on a website — [[external-secrets-operator]] configures OpenBao
with its **`vault` provider**, because from ESO's side there is nothing to distinguish them (§7.5).

> [!warning] Do not repeat the cost argument for Vault itself
> Vault **Community** Edition is free to run. "We use OpenBao because Vault costs money" is false at
> the CE tier — there the gate is the licence, not the invoice. The invoice is real one tier up, at
> Enterprise, which is what an enterprise actually buys.

**Where it genuinely does not teach the same thing.** Sentinel policy-as-code, performance and
disaster-recovery replication, HSM auto-unseal and seal wrapping, and control groups are Vault
**Enterprise** features. This platform teaches none of them, because neither Vault CE nor OpenBao has
them — the gap is against Vault Enterprise, not against OpenBao. Namespaces are the partial exception:
OpenBao shipped its own in **2.3 (beta, May 2025)**, API-compatible with Vault Enterprise's but
explicitly **not** storage- or operator-API-compatible
([announcement](https://openbao.org/blog/namespaces-announcement/)). Rule of thumb: assume the
application-facing API matches; verify anything operator-facing against OpenBao's docs, not Vault's.

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

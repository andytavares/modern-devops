---
type: concept
tags: [security, secrets, operations]
date_added: 2026-08-17
date_updated: 2026-08-17
---

# Secrets management

> [!info] One-liner
> The reference lives in git; the value lives in a vault and is pulled by the cluster. Rotation becomes a vault operation with no deploy, and CI never sees a secret.

## Four options, three of them bad (§7.1)

| Approach | Problem |
|---|---|
| Secrets in git, plain | Catastrophic. |
| Secrets in git, sealed/encrypted (SOPS, Sealed Secrets) | Works, but rotation means a commit and a deploy, and **revocation is impossible** — the old ciphertext is in history forever. |
| Secrets injected by CI | CI now holds every production secret. **Your build system becomes the highest-value target in the company.** |
| **Secrets in a vault, pulled by the cluster** | Rotation is a vault operation with no deploy. Access is audited per-identity. CI never sees them. |

A Kubernetes `Secret` is base64-encoded, **not encrypted**. Anyone with `get secret` in a namespace
reads it in plaintext.

## The shape here

[[openbao]] (KV v2 at mount `shop`) → [[external-secrets-operator]] → an ordinary Kubernetes `Secret`
→ a pod consumes it normally. Three constraints do all the work:

- **Capability.** `shop-read` grants `read` and nothing else — ESO cannot write, delete, or list secret
  values.
- **Identity binding.** The role is bound to one ServiceAccount in one namespace, so a compromised pod
  elsewhere cannot assume it.
- **Lifetime.** `ttl=1h`, so a stolen token expires within the hour.

**Every vault does it the same way.** Learn the three and the product is a detail.

## Path is the authorization boundary

Policies are written against path globs. `<namespace>/<app>` makes "order-api may read
`shop/order-api/*` and nothing else" one line. Flatten everything into `secret/` and every policy
becomes an enumeration of individual keys that rots immediately. **Design your secret paths before you
write your first policy** (§7.3).

Corollary: KV v2 stores data under `<mount>/data/<path>`. A policy written `path "shop/*"` instead of
`path "shop/data/*"` produces `SecretSyncedError, permission denied` — the second most common mistake
with KV v2.

## Human and machine paths are separate, and the human one has to be built

The machine path is genuinely least-privilege from §7.4. **The human path was the root token the entire
time** — every operator write in §7.3 ran as root. §7.5a builds the replacement: `userpass`, a scoped
`shop-admin` policy, an `operator` user. Bootstrapping that first non-root path is itself a root
operation; there is no way around it, and it is the last thing root should be used for.

**It is not a boundary until you have seen it refuse something.** `$BAO_OP auth list` → `403 permission
denied` is the point of the section.

## Three timing traps, and they are the part people get wrong

1. **A Secret changing is not a pod using it.** Env vars are set at container start; mounted volumes
   update lazily. The real rotation window is `refreshInterval` + time-until-restart. **Measure your
   real rotation window, do not assume it** (§15.4).
2. **`Ready=True` while serving a stale value is truthful.** The ExternalSecret *is* synced — to the
   previous version. Force it with a `force-sync` annotation, and diagnose without printing the secret
   by comparing decoded **length** and `bao kv metadata get`'s newest `created_time` against
   `.status.refreshTime`.
3. **The loop fails when the vault is not the only authority.** [[postgresql]] was initialised with its
   password on first boot and does not learn a new one from a Secret, so rotating in OpenBao alone
   locks [[backstage]] out of its own database. Rotate at **both** ends.

> **Before you automate rotation for anything, ask which side owns the value.**

## One credential, two Secret types

`nexus-push` (Opaque, a [[buildah]] auth file) and `nexus-pull` (`kubernetes.io/dockerconfigjson`, for
the kubelet) are the same OpenBao entry rendered twice, because two different consumers want two
different shapes. And **Secrets do not cross namespaces**, so the pull secret is declared separately in
`shop`, `buildkite` and `backstage`.

## What is still seeded by hand

The Buildkite git credential and the [[argo-cd]] repo credential, both imperative, because Buildkite
must be able to clone before it can run the pipeline that would otherwise create them. **Bootstrap
always has one manual seed; the discipline is keeping it to one** (§12.3).

## Related

[[openbao]] · [[external-secrets-operator]] · [[postgresql]] · [[backstage]] · [[buildkite]] · [[argo-cd]] · [[gitops]]

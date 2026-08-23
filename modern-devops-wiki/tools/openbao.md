---
type: tool
tags: [secrets, security]
role: the source of truth for every secret on the platform
version: chart 0.29.1 (OpenBao 2.6.1)
docs: https://openbao.org/docs/
date_added: 2026-08-17
date_updated: 2026-08-23
status: in-use
---

# OpenBao

> [!info] One-liner
> The Linux Foundation's MPL fork of the last open-source HashiCorp Vault, API-compatible with it. Everything secret in this platform originates here and reaches pods through [[external-secrets-operator]].

## What it holds

KV **v2** at mount point `shop` (§7.3). v2 gives versioning and soft-delete; v1 is a flat overwrite
with no history.

| Path | Keys | Consumed by |
|---|---|---|
| `shop/order-api` | `signing_key` | order-api's `ORDER_SIGNING_KEY` (§7.6) |
| `shop/nexus` | `username`, `password` | `nexus-pull` in `shop`/`buildkite`/`backstage`, `nexus-push` in `buildkite` |
| `shop/backstage` | `github_token`, `postgres_password`, `postgres_admin_password` | [[backstage]] and its [[postgresql]] (§14.8) |

> **Path *is* the authorization boundary.** Policies are written against path globs, so
> `<namespace>/<app>` makes "order-api may read `shop/order-api/*` and nothing else" one line. Flatten
> everything into `secret/` and every policy becomes an enumeration that rots immediately (§7.3).

## Two auth methods, two identities

**Machine — `kubernetes` (§7.4).** A pod presents its projected ServiceAccount JWT; OpenBao calls
Kubernetes `TokenReview` to verify it. That needs `system:auth-delegator` on OpenBao's own
ServiceAccount. Role `eso` is bound to SA `external-secrets` in ns `external-secrets`, policy
`shop-read` (read on `shop/data/*`, read+list on `shop/metadata/*`), `ttl=1h`. Capability, identity
binding, lifetime — that is the whole of secrets access control.

**Human — `userpass` (§7.5a).** Policy `shop-admin` adds `create`/`update` on `shop/data/*` and
nothing else. Both paths, plus the KV mount and its data, are packaged as a re-runnable Job in
`deploy/platform/openbao-bootstrap.yaml`, because dev-mode OpenBao loses everything on restart.

The section is only finished when you have seen it **refuse** something:

```
$BAO_OP auth list
Code: 403. Errors: * permission denied
```

The operator can rotate every credential on this platform and cannot enable an auth method, mount an
engine, read a policy, or widen its own grant.

> [!warning] Do not pass `token_reviewer_jwt` or `kubernetes_ca_cert`
> Omitting them is the documented configuration for an OpenBao inside the cluster it authenticates
> against — it then reads both from its own service account mount **on every request**. Passing them
> explicitly looks more careful and is the opposite: since Kubernetes 1.21 the projected token is
> bound and short-lived (~1h, rotated at ~80% of life), so `token_reviewer_jwt="$(cat $SA/token)"`
> freezes a snapshot. Everything works, then an hour later every TokenReview fails `permission
> denied`, the `ClusterSecretStore` flips to `Invalid`, and every `ExternalSecret` in the cluster
> stops refreshing — long after the setup you verified as green (§7.4, Appendix B).

> [!warning] `bao kv put` is a full overwrite of the version
> `kv put shop/backstage github_token=...` on a path that also holds `postgres_password` destroys the
> other keys. `kv patch` needs a separate `patch` capability and `shop-admin` deliberately does not
> grant it. Write every key of a path in one command (§7.5a, §14.8).

## What a restart actually costs, and what the 403 is really saying

Observed 2026-08-23. `openbao-0` had restarted ~5h earlier (`RESTARTS 1`). The symptom, surfaced in
[[argo-cd]] via [[external-secrets-operator]]:

```
unable to log in to auth method: unable to log in with Kubernetes auth:
URL: PUT http://openbao.openbao.svc.cluster.local:8200/v1/auth/kubernetes/login
Code: 403. Errors: * permission denied
```

`ClusterSecretStore/openbao` was `InvalidProviderConfig`, and both `ExternalSecret`s in `shop` were
`SecretSyncedError`. What OpenBao actually held:

| | Before | After the restart |
|---|---|---|
| auth methods | `token`, `kubernetes`, `userpass` | `token`, `userpass` |
| secret engines | `secret`, `shop` (kv v2) | `secret` |
| policies | `default`, `root`, `shop-read`, `shop-admin` | `default`, `root`, `shop-admin` |
| `auth/kubernetes/role/eso` | present | `No value found` |

> [!warning] A 403 on `/v1/auth/kubernetes/login` does not mean the role is wrong
> **OpenBao answers "your role does not match" and "that auth method does not exist" identically.**
> The error names Kubernetes auth, so it reads like a ServiceAccount or TokenReview problem, and the
> first instinct is to go audit `bound_service_account_names`, the `system:auth-delegator` binding and
> the projected token. All of that was fine. `bao auth list` is the cheap first check: if `kubernetes/`
> is not in the output, nothing about ESO is broken. Compare the *other* way this store goes invalid —
> a pinned `token_reviewer_jwt` expiring — which produces the same words for an entirely different
> reason (§7.4, Appendix B).

Why only half came back: the Job at `deploy/platform/openbao-operator-auth.yaml` restored `userpass`,
`shop-admin` and the `operator` user — and its header comment asserted *"the machine path already
exists"*, which is true exactly until the first restart. §7.3's mount and §7.4's kubernetes auth were
hand-typed shell, so they lived nowhere but in the reader's terminal history.

Fixed 2026-08-23: the Job became `deploy/platform/openbao-bootstrap.yaml` and now covers §7.3, §7.4
and §7.5a in build order, plus the `system:auth-delegator` ClusterRoleBinding declaratively. Recovery
is `kubectl delete -f` then `kubectl apply -f` — delete-then-apply because a Job's pod template is
immutable. Verified: ESO went to `Valid`/`SecretSynced` within 15s of the Job completing.

> [!info] The idempotency that matters is not "enable is a no-op"
> Enabling an enabled mount and rewriting a policy are already no-ops. The one that bites is
> `kv put`: a re-run that regenerated `shop/order-api`'s `signing_key` would leave every running
> `order-api` pod holding the previous value, because env vars are read at process start. The Job
> reads each path first and seeds **only what is missing**. `signing_key` is safe to regenerate when
> it is genuinely lost — order-api HMACs each payload into S3 and nothing ever verifies it — but that
> is a property of this key, not a licence to overwrite secrets on every apply.

> [!warning] `nexus-password` in the `openbao-bootstrap` Secret is a third copy of one credential
> Nexus owns the `ci` user's password. OpenBao holds a copy at `shop/nexus`. The bootstrap Secret now
> holds another, and it is the one that wins on every restart, because that is when the Job re-seeds a
> missing path. Seeding it from the tutorial's documented `ci-password-change-me` on 2026-08-23 broke
> CI's `buildah push` — see [[sonatype-nexus]] for why the symptom arrived as a 429 rather than a 401.
> Rotate the Nexus password and you must rotate all three, or the next OpenBao restart reintroduces
> the mismatch hours after the change that caused it. Same shape as the [[postgresql]] row in
> Appendix B: **a secret with two ends drifts, and the drift surfaces on a restart, not on the edit.**

## Dev mode, stated as the loaded gun it is

`server.dev.enabled=true` gives in-memory storage (lost on restart), auto-unseal at boot, TLS
disabled, and a root token you typed into your shell history. Production is the opposite of all four:
Raft on persistent volumes, KMS/HSM auto-unseal, end-to-end TLS, and no long-lived root token. Dev
mode exists so you learn the *data model* without also learning the *operations model* on day one
(§7.2).

The root token is **not revoked here and cannot be** — dev mode recreates it on every pod restart. In a
real cluster the last step of §7.5a is `bao token revoke <root-token>`, after which a new one exists
only via `bao operator generate-root` with a quorum of unseal-key holders. That quorum is the design:
root is an event several people agree to, not a string in someone's history.

## The agent injector is off, deliberately

`injector.enabled=false`. The injector is the other valid pattern — a mutating webhook writes secrets
to a shared volume as files, giving live rotation with no pod restart and never creating a Kubernetes
`Secret` at all, which is strictly better isolation. ESO's advantage is that the result **is** an
ordinary Secret, so anything consumes it: image pull secrets, TLS certs, third-party charts that only
accept a secret name. §7.6 needs exactly that. Pick the injector when your app reads files and you
want nothing in etcd; pick ESO when you need interoperability (§7.2).

## OpenBao vs Vault, precisely

[[enterprise-substitution]]. What transfers: paths, ACL policy documents, KV v2 and its
`/data/`–`/metadata/` split, the Kubernetes auth method and its TokenReview dependency, tokens and
leases, and the `bao`/`vault` CLI verbs. The concrete proof is that ESO drives OpenBao through its
**`vault` provider** — there is no `openbao:` key, and expecting one is the most common mistake here.

Where it stops: Vault *Community* is free to run, so "we picked OpenBao because Vault costs money"
would be a lie — the **licence** is the gate (Vault moved to BUSL in 2023), not the invoice. The
invoice is one level up, and that is the real teaching gap: Sentinel policy-as-code, performance and
DR replication, HSM auto-unseal and seal wrapping, and control groups are Vault **Enterprise**
features that neither Vault CE nor OpenBao has. Namespaces are the partial exception — OpenBao shipped
its own in 2.3 (beta, May 2025), API-compatible but not storage- or operator-API-compatible. Assume
the *application-facing* API matches; verify anything operator-facing against OpenBao's own docs.

## Related

[[external-secrets-operator]] · [[secrets-management]] · [[enterprise-substitution]] · [[backstage]] · [[postgresql]] · [[kubernetes]]

---
type: tool
tags: [secrets, operator]
role: projects OpenBao values into ordinary Kubernetes Secrets
version: chart 2.6.0
docs: https://external-secrets.io/latest/
date_added: 2026-08-17
date_updated: 2026-08-17
status: in-use
---

# External Secrets Operator

> [!info] One-liner
> A controller that reads [[openbao]] on an interval and writes the result into a Kubernetes `Secret`. The reference lives in git; the value never does.

## What it does here

One `ClusterSecretStore` named `openbao` (`deploy/platform/secret-store.yaml`), then one
`ExternalSecret` per consumer:

| ExternalSecret | Namespace | Target type | Refresh |
|---|---|---|---|
| `nexus-pull` | `shop` | `kubernetes.io/dockerconfigjson` | 1h |
| `order-api-secrets` | `shop` | Opaque (`ORDER_SIGNING_KEY`) | 1m |
| `nexus-push` | `buildkite` | **Opaque** — a [[buildah]] auth file | 1h |
| `nexus-pull` | `buildkite` | `kubernetes.io/dockerconfigjson` | 1h |
| `backstage` | `backstage` | Opaque (`GITHUB_TOKEN`) | 1h |
| `backstage-postgresql-auth` | `backstage` | Opaque (`user-password`, `admin-password`) | 1h |
| `nexus-pull` | `backstage` | `kubernetes.io/dockerconfigjson` | 1h |

**The `vault` provider drives OpenBao.** There is no `openbao:` provider key. This is correct, not a
typo (§7.5).

**Secrets do not cross namespaces.** The same Nexus credential appears three times because
`shop`'s `nexus-pull` is invisible from `buildkite` and `backstage` (§12.4, §14.8). And the *same*
credential appears twice inside `buildkite` in two different Secret **types**, because Buildah reads a
plain auth file while the kubelet requires `dockerconfigjson` for an `imagePullSecret`.

**Templating is the reason ESO was chosen over the OpenBao injector.** `target.template` turns two KV
properties into a whole `.dockerconfigjson`, `b64enc` and all — the pattern that made `imagePullSecret`
work from a vault (§7.6).

**`creationPolicy: Owner`** means ESO garbage-collects the Secret if the `ExternalSecret` is deleted.
Otherwise deleting the declaration leaves an orphaned credential in the cluster.

## Three timing traps, all real

> [!warning] `refreshInterval` is a rotation budget, not a preference
> ESO rewrites the Secret on this interval — but **a running pod does not see the change.** Env vars
> are set at container start and mounted volumes update lazily. The real rotation window is
> `refreshInterval` + time-until-pod-restart. Setting `1m` and assuming rotation takes a minute is a
> mistake people make in production (§7.6). Mount as a volume and re-read in-process, or add
> [Reloader](https://github.com/stakater/Reloader).

> [!warning] `Ready=True` is truthful and still not what you want
> A credential just written to OpenBao is rejected while the `ExternalSecret` reports `Ready=True` the
> whole time — it *is* synced, to the previous value. Restarting the consumer does not help. Force it:
> `kubectl -n <ns> annotate externalsecret <name> force-sync="$(date +%s)" --overwrite`, then restart.
> Diagnose **without printing the secret**: compare decoded length
> (`... | base64 -d | wc -c`) and `bao kv metadata get <path>`'s newest `created_time` against
> `.status.refreshTime` (Appendix B).

> [!warning] The loop does not work when OpenBao is not the only authority
> [[postgresql]] was initialised with its password on first boot and does not learn a new one from a
> Secret. Rotating `shop/backstage`'s `postgres_password` in OpenBao alone locks [[backstage]] out of
> its own database. Rotate at **both** ends (§15.4). Before automating rotation for anything, ask
> which side owns the value. See [[secrets-management]].

## Failure modes worth memorising

- **`ClusterSecretStore Invalid`** — usually a pinned `token_reviewer_jwt` that expired, a missing
  `system:auth-delegator` binding, or a role-name mismatch. Check `bao read auth/kubernetes/config`
  first (Appendix B, and [[openbao]]).
- **`SecretSyncedError`, `permission denied`** — the KV v2 policy is missing the `/data/` segment.
  It must be `path "shop/data/*"`, not `path "shop/*"` (§7.4).
- **[[argo-cd]] parks the `platform` Application on `OutOfSync` forever** — the ESO CRD defaults a pile
  of fields the API server injects (`deletionPolicy`, `engineVersion`, `mergePolicy`,
  `conversionStrategy`, `decodingStrategy`, `metadataPolicy`, `nullBytePolicy`) that are not in git.
  The fix is `argocd.argoproj.io/compare-options: ServerSideDiff=true` plus `ServerSideApply` (§11.4).

## `ClusterSecretStore` vs `SecretStore`

Namespaced stores mean teams configure their own connection and cannot reach each other's. A
`ClusterSecretStore` is one shared definition — less duplication, but any namespace can reference it,
so isolation now depends entirely on the OpenBao policy rather than on Kubernetes RBAC. Used here
because there is one team; use namespaced stores the moment there are two (§7.5).

## Related

[[openbao]] · [[secrets-management]] · [[kubernetes]] · [[argo-cd]] · [[buildkite]] · [[backstage]]

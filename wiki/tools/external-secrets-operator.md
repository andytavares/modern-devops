---
type: tool
tags: [secrets, security, operator]
role: Syncs secrets from OpenBao into Kubernetes Secrets
version: chart 2.6.0
docs: https://external-secrets.io/latest/
date_added: 2026-08-15
date_updated: 2026-08-15
status: in-use
---

# External Secrets Operator (ESO)

> [!info] One-liner
> A controller that reads from a real secret manager and writes Kubernetes Secrets, so no secret is ever committed to git.

## What it is

An operator with two main CRDs:

- **`ClusterSecretStore` / `SecretStore`** — *where* secrets come from and how to authenticate.
- **`ExternalSecret`** — *which* secrets to fetch and what Kubernetes Secret to write.

It closes the gap that makes [[gitops]] awkward: everything else can live in git, but a Secret
cannot, because a Kubernetes Secret is base64 — encoding, not encryption. ESO lets git hold a
*reference* while the value stays in [[openbao]].

## What it does here

One `ClusterSecretStore` named `openbao` using the **`vault` provider** (OpenBao is API-compatible —
there is no `openbao` provider key), authenticated via Kubernetes auth (§7.5). Then:

| ExternalSecret | Namespace | Produces |
|---|---|---|
| `order-api-secrets` | `shop` | the HMAC signing key, refreshed every 1m |
| `nexus-pull` | `shop` | a `dockerconfigjson` image-pull secret |
| `nexus-push` | `buildkite` | a plain auth file for [[buildah]] (Opaque, not dockerconfigjson) |
| `backstage` | `backstage` | the portal's `GITHUB_TOKEN` |

The `nexus-push` case is instructive: Buildah wants a plain `config.json`, not a Kubernetes
`dockerconfigjson` type. Same JSON shape, different Secret type — so ESO **templates** it as Opaque.

## Key concepts

- **`refreshInterval` is a poll, not a push.** And even after the Secret updates, running Pods keep
  the old value — env vars are set at container start. Rotation = update + resync + restart (§15.4).
- **Templating** lets one ExternalSecret assemble a composite Secret from several remote keys.
- `creationPolicy: Owner` means ESO owns the Secret's lifecycle: delete the ExternalSecret, the
  Secret goes too.

## Gotchas

- `SecretSyncedError` with `permission denied` is almost always the missing `/data/` segment in the
  OpenBao policy — see [[openbao]].
- A store stuck `Invalid` usually means the TokenReview RBAC or a role-name mismatch.

## Official docs

- Docs: https://external-secrets.io/latest/
- Vault provider (used for OpenBao): https://external-secrets.io/latest/provider/hashicorp-vault/
- OpenBao provider notes: https://external-secrets.io/latest/provider/openbao/

> [!tip] Related
> [[openbao]], [[secrets-management]], [[gitops]], [[argo-cd]]

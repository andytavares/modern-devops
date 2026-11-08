---
type: tool
tags: [database, portal]
role: Backstage's catalog and scaffolder state
version: bundled Bitnami subchart of Backstage chart 2.10.0 (`bitnamilegacy` image)
docs: https://www.postgresql.org/docs/
date_added: 2026-08-17
date_updated: 2026-08-17
status: in-use
---

# PostgreSQL

> [!info] One-liner
> The only stateful thing in this platform that is not [[apache-kafka]]. It exists solely to hold [[backstage]]'s catalog, and it is the component most likely to lock you out of your own portal.

## What it does here

`postgresql.enabled: true` in `infra/backstage-values.yaml` brings up the Backstage chart's bundled
Bitnami subchart as a StatefulSet in the `backstage` namespace. User `bn_backstage`. Credentials come
from [[openbao]] through [[external-secrets-operator]] as the `backstage-postgresql-auth` Secret.

## Three ways it breaks, all documented in anger

> [!warning] The Secret's key names are **not** the Bitnami defaults
> The Secret the subchart generates for itself holds `password` and `postgres-password`, but those
> literals live only in the no-`existingSecret` branch of its helpers. Once
> `postgresql.auth.existingSecret` is set, the names come from `postgresql.auth.secretKeys.*` — and the
> Backstage chart **overrides** the Bitnami defaults there to **`user-password`** and
> **`admin-password`**. Copy the names off the generated Secret and `helm upgrade` dies with
> `PASSWORDS ERROR: The secret "backstage-postgresql-auth" does not contain the key "user-password"`.
> Both keys are required (`auth.enablePostgresUser` defaults to true); `replication-password` is not,
> because it is read only under `architecture: replication` (§14.8, Appendix B).

> [!warning] The ExternalSecret must exist **before** the install
> With `existingSecret` set the subchart no longer creates the Secret and does not wait for one. It
> reads the keys at render time and fails if the object is absent. The install order in §14.8 is a
> dependency, not a preference.

> [!warning] Rotating the password in OpenBao alone locks Backstage out
> Postgres initialises its data directory **once**, on first boot, with the password it saw then. It
> does not learn a new one from a Secret. Change `shop/backstage`'s `postgres_password` in OpenBao and
> Backstage restarts presenting a password the server rejects:
> `password authentication failed for user "bn_backstage"`. Rotate at both ends — `ALTER ROLE` in
> Postgres, then OpenBao, then restart (§15.4). This is the exception to the otherwise-clean rotation
> loop in [[secrets-management]].

## And one that has nothing to do with credentials

Anything that restarts Postgres — a node reboot, a `helm upgrade` rolling the StatefulSet — leaves the
Backstage backend **permanently** broken with `Failed to instantiate service 'core.auth'`, an error
naming neither Postgres nor the restart. Backstage does not retry plugin initialisation after the
database goes away. The fix is `kubectl -n backstage rollout restart deploy/backstage` (Appendix B).

## The `bitnamilegacy` smell

The chart's default points at Bitnami's **legacy** registry, which is where images go once they stop
being the maintained line. It works, and for a laptop it is fine. For anything durable, run Postgres
you control — an operator, or a managed database — with `postgresql.enabled: false` and `POSTGRES_*`
pointing at it. **Never let your portal's database be the least-maintained component in your
platform**: when it dies you lose the catalog, and the catalog is what you would have used to find out
what depends on it (§14.8). Which operator to use is an [[open-questions]] entry.

## Related

[[backstage]] · [[openbao]] · [[external-secrets-operator]] · [[secrets-management]] · [[helm]]

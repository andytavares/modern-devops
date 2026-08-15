---
type: tool
tags: [database]
role: Backstage's catalog and scaffolder state
version: bundled bitnamilegacy image via the Backstage chart
docs: https://www.postgresql.org/docs/
date_added: 2026-08-15
date_updated: 2026-08-15
status: in-use
---

# PostgreSQL

> [!info] One-liner
> The only stateful store in this platform that isn't Kafka — it backs Backstage.

## What it does here

Deployed as the Backstage Helm chart's bundled subchart (§14.8), holding the catalog, scaffolder task
state and plugin data. Credentials wired through `POSTGRES_*` environment variables.

> [!warning] The bundled image is `bitnamilegacy/postgresql`
> Bitnami's catalogue changes in 2025 broke a lot of charts, and this chart's default now points at
> the legacy registry. It works and is fine for a laptop. For anything durable, run Postgres you
> control — an operator or a managed database — and set `postgresql.enabled: false`.
>
> **Never let your portal's database be the least-maintained component in your platform**: when it
> dies you lose the catalog, and the catalog is what you'd use to find out what depends on it.

## Open questions

- Which Postgres operator (CloudNativePG, Zalando, Crunchy) fits this stack best if we replace the
  bundled subchart?

## Official docs

- Docs: https://www.postgresql.org/docs/

> [!tip] Related
> [[backstage]], [[kubernetes]]

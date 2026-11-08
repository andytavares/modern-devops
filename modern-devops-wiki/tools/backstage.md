---
type: tool
tags: [portal, paved-paths, catalog]
role: catalog plus the two paved paths
version: chart 2.10.0; create-app 1.53.x (repo backstage.json says 1.53.0, Appendix A says 1.53.1)
docs: https://backstage.io/docs/
date_added: 2026-08-17
date_updated: 2026-08-17
status: documented-not-observed
---

# Backstage

> [!info] One-liner
> The thing that turns this platform from a system into a product. The test is not whether *you* can add the next service — it is whether someone who has read none of this can.

> [!warning] Backstage is a framework, not a product
> You do not install Backstage; you **build** a Backstage. `create-app` scaffolds a TypeScript
> monorepo that is now *your code*, and adding a plugin means editing
> `packages/backend/src/index.ts` and rebuilding an image. That is the deal, and it is why this repo
> builds its own image rather than running the public demo one — the demo's plugin set is fixed, and
> the first thing you want is a plugin it does not have.

## The two parts used

**The catalog** — `catalog-info.yaml` at the repo root: one `System`, four `Component`s (order-api,
order-worker, pricing, frontend), two `API`s (orders, pricing), one `Resource` (orders-raw), one
`Group` (platform).

> **`definition.$text` points at the generated artefact, never a copy.** `API/orders` points at
> `services/order-api/openapi.json`, emitted from the routes and guarded by a drift test.
> `API/pricing` points at `protos/shop/v1/pricing.proto` — the same file [[pants]] compiles into both
> the Python server and the Go stubs, so **there is no second copy to drift from.** An API entity whose
> definition is a hand-maintained second copy is worse than no API entity at all.

> **`dependsOn: [resource:default/orders-raw]` is the line that earns the catalog its keep.** "What
> breaks if this bucket goes away" becomes a query rather than an archaeology project. Ownership and
> dependency edges are the only two pieces of catalog metadata that consistently pay for their
> maintenance; the rest is decoration until proven otherwise.

**The scaffolder** — templates that take a form and produce a **pull request**, never a direct push to
`main`. *A paved path that bypasses review is not a path, it is a hole.* See [[paved-paths]].

| Template | Produces |
|---|---|
| `new-service` | `services/<name>/` (code, tests, `BUILD`, `Dockerfile`) + one chart file |
| `new-bucket` | `deploy/platform/infra/<name>.yaml`, applied by [[argo-cd]] |

Both work because of decisions made earlier: [[buildkite]] discovers services from the filesystem and
Argo CD recurses `deploy/platform`. **Neither template edits a pipeline, and neither touches the
cluster.**

## `catalog.rules` is not boilerplate

It is the allow-list of entity kinds a location may introduce. Without it, anyone who can open a PR to
a catalogued repo can introduce a `Template` — **and a Template is code that runs in your scaffolder
with your GitHub token.** That is why a catalog file is safe to accept from a service team and a
template file is not (§14.4).

## Building it, which is where the time goes

**Use `portal/Dockerfile`** (Backstage's documented multi-stage build), not the
`packages/backend/Dockerfile` `create-app` generates. That one is a *host build* expecting a `dist/`
you produced beforehand with a local Node toolchain, and CI's build step is a [[buildah]] pod with no
Node in it. The multi-stage file compiles inside the image, so `buildah bud` is self-contained.
Slower — that is the trade for not needing Node in CI.

> [!warning] Leave `packages/*/src` **commented out** in `.dockerignore`
> `create-app` writes that exclusion for the host build. The multi-stage build compiles *from* those
> sources, and excluding them fails with `error TS18003: No inputs were found in config file
> '/app/tsconfig.json'` — an error naming `tsconfig.json` that **never mentions Docker**. `plugins`
> stays excluded, because `portal/plugins/` holds only a README and the matching `COPY` is commented
> out.

**Twenty to forty-five minutes in a `vfs`-backed privileged pod.** The portal step is
`branches: "main"` only for that reason. While iterating, build on your laptop.

npm resolves through [[sonatype-nexus]]' `npm-proxy` because `.yarnrc.yml` is copied in before
`yarn install`. `create-app` also writes `npmMinimalAgeGate` and `npmPreapprovedPackages`, which are
worth keeping rather than deleting — Nexus controls *where* a dependency comes from, the gate controls
*how battle-tested* it is. That is [[supply-chain-choke-point]] applied to time instead of location.

> [!warning] Do not run `yarn set version` after `create-app`
> It pins the version it wants in `package.json`'s `packageManager` and Corepack honours it. A second
> pin buys nothing, and an **older** one makes the scaffold unable to read the `.yarnrc.yml` it just
> wrote. If you must move it, move it forwards.

## Configuration traps, all of which were hit

> [!warning] The chart's `command` discards the image's `CMD`
> `infra/backstage-values.yaml` must repeat the `--config` flags as `backstage.args`. Without them
> Backstage loads only `app-config.yaml`, whose database block is `better-sqlite3` `:memory:` for local
> dev, then dies loading a native binding that was never compiled — and **every plugin fails with
> `Failed to instantiate service 'core.auth'`**, an error naming neither the config nor the database.

> [!warning] `https://backstage.localtest.me`, never `http://`
> The frontend calls `crypto.randomUUID`, which browsers expose **only in a secure context**. Over
> plain http the UI loads a blank white page and nothing else. This is a browser restriction, not a
> Backstage bug — and every URL the portal knows about itself must agree, which is why
> `app-config.production.yaml` uses `https` throughout.

> [!warning] `backend.listen` must be the object form, with `host: 0.0.0.0`
> The string shorthand (`listen: ':7007'`) is rejected with
> `Invalid type in config for key 'backend.listen', got string, wanted object`. And the default host is
> `127.0.0.1`, so the container binds to loopback and the kubelet's probes never reach it.

> [!warning] `backend.add(import('@backstage/plugin-scaffolder-backend-module-github'))`
> In the new backend system every provider's actions ship as their own module and none are on by
> default. Without this line `publish:github:pull-request` does not exist and every template run fails
> at the **last** step with "action not found" — after doing all the work.

> [!warning] Do not add `POSTGRES_*` to `extraEnvVars`
> With `postgresql.enabled: true` the chart already emits them, and a second copy fails the install
> outright — server-side apply treats `env` as a list keyed by `name` and rejects duplicate keys.

The [[postgresql]] Secret key names, the ordering constraint on the `ExternalSecret`, and the
rotation trap are on that page.

## The GitHub token

Fine-grained PAT, **this repository only**: `Contents: Read-only` (reads `catalog-info.yaml` and the
two template files) and `Pull requests: Read and write` (the scaffolder opens PRs). **Contents alone is
not enough to open a PR** — the symptom is a 403 at the last step (Appendix B). It reaches the cluster
from [[openbao]] through [[external-secrets-operator]] like every other secret.

## Two things stated plainly, because they are the honest cost

> **The portal is the one thing here still deployed by `helm install` from your laptop** —
> imperatively, outside [[gitops]], with a tag set by hand. A deliberate stopping point: making it an
> Argo CD Application and teaching CI to bump its tag is §11.4 and §12.5 applied one more time, and
> doing it yourself is a better test than reading a third worked example. Note the irony — **the tool
> whose entire job is paving paths is, right now, the least paved thing in the cluster.** That is how
> platforms usually look.

> **Guest sign-in means there is no such thing as "who did that".** Every scaffolder run and every PR
> is attributed to the one GitHub token, so the audit trail says "the portal did it" and stops.
> Tolerable on a laptop and indefensible anywhere else, because **the portal's token is more privileged
> than any individual's.** The production shape is GitHub OAuth for user identity plus the scaffolder
> acting as a GitHub App. Wire that up before a *second* person uses your portal.

## Known regression

The `new-service` skeleton now emits a `BUILD` file, which is what makes a scaffolded service a
first-class Pants target. That fixed the regression the Pants migration introduced. What remains open
is whether a service has ever actually been scaffolded end to end — see [[open-questions]].

## Status

Documented, not observed — the §14–§16 block has never been run against a live cluster in this repo.

## Related

[[paved-paths]] · [[postgresql]] · [[openbao]] · [[external-secrets-operator]] · [[argo-cd]] · [[buildkite]] · [[pants]] · [[grpc]] · [[order-platform]] · [[supply-chain-choke-point]]

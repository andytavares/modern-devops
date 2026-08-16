---
type: tool
tags: [portal, developer-experience, paved-paths]
role: Developer portal — catalog plus the two paved paths
version: chart 2.10.0, create-app 1.53.1
docs: https://backstage.io/docs/overview/what-is-backstage
date_added: 2026-08-15
date_updated: 2026-08-16
status: in-use
---

# Backstage

> [!info] One-liner
> A framework for building a developer portal — here, a software catalog plus scaffolder templates that turn a form into a reviewed pull request.

## What it is

> [!warning] Backstage is a framework, not a product
> You do not install Backstage; you **build** one. `npx @backstage/create-app` scaffolds a TypeScript
> monorepo that is now *your code*, and adding a plugin means editing `packages/backend/src/index.ts`
> and rebuilding an image. That is the deal, and it is why this project builds a custom image rather
> than running the public demo one — the demo's plugin set is fixed, and the first thing you want is a
> plugin it lacks.

Two parts matter here:

- **The catalog** — entities (`Component`, `System`, `Resource`, `Group`, `API`, `Template`) declared
  in YAML next to the code, so ownership is reviewed like code.
- **The scaffolder** — templates that take a form and run actions. Ours produce **pull requests**,
  never direct pushes. A paved path that bypasses review is not a path, it's a hole.

## What it does here

Built by our own [[buildkite]] pipeline, pushed to [[sonatype-nexus]], deployed with the community
Helm chart at `backstage.localtest.me` (§14.8). Secrets via [[external-secrets-operator]] from
[[openbao]]. npm dependencies proxied through Nexus (§14.2).

Two paved paths (§14.6–14.7):

| Template | Produces | Why it needs no CI or CD changes |
|---|---|---|
| **New service** | `services/<name>/` + one chart file | CI globs `services/*/Dockerfile`; the chart globs `services/*.yaml` |
| **New S3 bucket** | `deploy/platform/infra/<name>.yaml` | [[argo-cd]]'s `platform` app recurses that directory |

## Key concepts

- **`catalog.rules` is a security control**, not boilerplate: it allow-lists the entity kinds a
  location may introduce. A `Template` is code that runs in your scaffolder with your GitHub token,
  which is why a catalog file is safe to accept from a service team and a template file is not.
- **Provider actions ship as separate modules.** `publish:github:pull-request` does not exist until
  you `backend.add(import('@backstage/plugin-scaffolder-backend-module-github'))` — and the failure is
  "action not found" *after* the template has done all its work.
- **Bias every paved-path step towards adding a file rather than editing one** (§14.6). Creation is
  conflict-free and trivially reviewable; editing a shared values file is neither.
- **A skeleton must inherit the platform's guarantees, or the paved path is a downgrade.** Ours ships
  a **templated `uv.lock`** — the project name appears in it exactly once, so the scaffolder rewrites
  it alongside `pyproject.toml` and the two still agree, keeping `uv sync --locked` working. The
  alternative, dropping `--locked` for scaffolded services only, would make the generated service less
  reproducible than the hand-written one it was copied from. The skeleton's `pyproject.toml` also
  declares the [[sonatype-nexus]] index for the same reason it is declared in [[uv]]: an index set
  only in CI can never match a committed lock, and omitting it sends every scaffolded service straight
  to `pypi.org` past the [[supply-chain-choke-point]] with no error.
- **Derive Prometheus metric prefixes in code, not in the template.** Service names are hyphenated and
  metric names may not be, so `SERVICE.replace("-", "_")` at runtime beats emitting
  `quotes-api_requests_total`, which fails at registration. A rename then cannot produce an invalid
  metric name.
- **Guest auth means there is no "who did that".** Every scaffolder run is attributed to one shared
  token. Production shape: GitHub OAuth for user identity plus a GitHub App so PRs are opened on
  behalf of the person who filled in the form.

## Gotchas

- Building the image in-cluster takes **20–40 minutes** with Buildah's `vfs` driver. Build on the host
  while iterating; let CI own it once stable.
- The bundled PostgreSQL uses a `bitnamilegacy` image — fine for a laptop, not for anything durable.
- New catalog files in an existing repo are **not** auto-discovered without a location entry or the
  GitHub discovery provider. This is the one seam the paved path leaves for a human (§14.7).

## Two Dockerfiles, and CI can only use one of them

`create-app` generates `packages/backend/Dockerfile`, which is a **host build**. Its own header says
so: it expects `yarn install --immutable && yarn tsc && yarn build:backend` to have already produced
`packages/backend/dist/`. It *copies* `skeleton.tar.gz`; it never creates it.

Our [[buildkite]] step is a [[buildah]] pod with no Node toolchain, so it must use Backstage's
[multi-stage Dockerfile](https://backstage.io/docs/deployment/docker#multi-stage-build) instead —
three stages: a skeleton layer of nothing but `package.json` files so dependency installs cache, a
build stage running the same `yarn tsc` / `yarn build` you would run by hand, and a production stage
carrying only the bundle and production dependencies. Slower than a host build; self-contained, which
is the point.

> [!warning] Pointing CI at the host-build Dockerfile — hit 2026-08-16
> ```
> STEP 12/18: COPY --chown=node:node yarn.lock package.json packages/backend/dist/skeleton.tar.gz ./
> Error: ... copier: stat: "/packages/backend/dist/skeleton.tar.gz": no such file or directory
> exit status 125
> ```
> Two minutes of pulling base layers before it fails, and the message names an artefact you have never
> heard of rather than saying "you skipped the build". Keep both files: the host build is faster while
> iterating, the multi-stage one is what CI can run.

> [!warning] `COPY plugins plugins` fails on a portal with no internal plugins
> Backstage's multi-stage Dockerfile carries `# Comment this out if you don't have any internal
> plugins` above that line — take it literally. `create-app` leaves `plugins/` holding only a
> `README.md`, **and `.dockerignore` excludes `plugins` outright**, so the glob matches nothing:
> `no items matching glob "/src/plugins" copied (1 filtered out using /src/.dockerignore)`.
> The two facts compound: even the README wouldn't have saved it.

> [!warning] The Helm chart discards the image's `CMD` — hit 2026-08-16
> Chart 2.10.0 sets `command: ["node","packages/backend"]` and `args: []`, replacing the Dockerfile's
> `CMD` and silently dropping its `--config` flags. Backstage then loads only `app-config.yaml`, the
> *development* config, whose database is `better-sqlite3` in `:memory:`. The production image has no
> compiled SQLite binding, so every plugin fails with `Failed to instantiate service 'core.auth'` and
> `Could not locate the bindings file ... better_sqlite3.node` — naming neither the config nor the
> database, for a database the deployment does not use.
>
> The tell is the first log line: `MergedConfigSource{...}` lists exactly which files were read. If
> `app-config.production.yaml` is missing from it, stop and fix `args` before debugging anything else.
>
> Liveness passes while readiness returns `{"message":"Backend has not started yet"}`, so the pod sits
> `0/1 Running` instead of crash-looping — a state that invites waiting rather than investigating.

> [!warning] `backend.listen` takes an object, not a string — hit 2026-08-16
> `listen: ':7007'` was valid in older Backstage and is now rejected:
> `Invalid type in config for key 'backend.listen', got string, wanted object`. Use the object form,
> and set `host: 0.0.0.0` — the `127.0.0.1` default binds to loopback, where the kubelet's probes
> cannot reach it.

> [!warning] The `backstage` namespace needs its own pull secret. Hit 2026-08-16
> ```
> Failed to pull image "nexus:8082/shop/portal:dev": pull access denied,
> repository does not exist or may require authorization:
> authorization failed: no basic auth credentials
> ```
>
> **Secrets do not cross namespaces.** §7's `nexus-pull` lives in `shop` and is invisible from
> `backstage`, and §14.8's `backstage-secrets.yaml` only created `GITHUB_TOKEN`. Two things were
> missing: a second [[external-secrets-operator]] `ExternalSecret` rendering a
> `kubernetes.io/dockerconfigjson` in this namespace, and `backstage.image.pullSecrets` in the values
> — the chart exposes it and defaults it to `[]`.
>
> Read the error carefully, because it conflates two different failures. *"repository does not exist
> **or** may require authorization"* is the registry declining to say which. Once the pull secret is
> attached the message changes to a plain `NotFound`, which is the **authenticated** answer and means
> the image genuinely isn't there. `no basic auth credentials` → missing Secret; `not found` → missing
> image. Confirmed by watching it flip from one to the other.

> [!warning] Don't set `POSTGRES_*` in `extraEnvVars` — the chart already does. Hit 2026-08-16
> With `postgresql.enabled: true`, chart 2.10.0 wires the backend to its own Postgres subchart and
> emits `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_USER` and `POSTGRES_PASSWORD`. Adding the same
> four via `extraEnvVars` renders each key twice and the install dies before creating anything:
>
> ```
> Error: server-side apply failed for object backstage/backstage apps/v1, Kind=Deployment:
>   .spec.template.spec.containers[name="backstage-backend"].env:
>     duplicate entries for key [name="POSTGRES_HOST"]   (and PORT, USER, PASSWORD)
> ```
>
> **Server-side apply treats `env` as a list keyed by `name` and rejects duplicates outright.**
> Client-side apply silently kept the last entry, which is why this pattern survives in older values
> files. The strictness is an improvement: two entries for one variable was always a bug, just a
> silent one. Confirmed the chart's generated values are byte-identical to the hand-added ones, so
> deleting the block changes nothing about the running pod.
>
> Keep `extraEnvVarsSecrets` — that is what injects `GITHUB_TOKEN`. And if you point Backstage at a
> database you control (`postgresql.enabled: false`), you *do* set `POSTGRES_*` yourself: that is the
> case `extraEnvVars` exists for, and there is no duplicate because the chart contributes nothing.
>
> **Clean up after the failed install before retrying.** The dead revision leaves a Helm-owned
> `backstage-postgresql` Secret whose keys don't match what the subchart's password-reuse check looks
> for, so the next run fails differently — `PASSWORDS ERROR: The secret "backstage-postgresql" does
> not contain the key "user-password"`. `helm uninstall backstage -n backstage` clears both, and the
> ESO-owned `backstage` Secret survives because Helm doesn't own it.

> [!warning] Never pin Yarn *backwards* after `create-app` — hit 2026-08-16
> The tutorial used to run `yarn set version 4.4.1` straight after scaffolding. `create-app@latest`
> writes supply-chain settings into `.yarnrc.yml` that a 4.4.1 binary cannot parse, so the scaffold
> becomes unable to read its own config:
>
> ```
> Usage Error: Unrecognized or legacy configuration settings found: npmMinimalAgeGate
>   (in portal/.yarnrc.yml)
> ```
>
> `npmMinimalAgeGate` — refuse packages published less than N ago — arrived in **Yarn 4.12**, with
> `npmPreapprovedPackages` to exempt `@backstage/*` from it. Nothing complains at scaffold time; the
> error waits until the first `yarn add`, which reads like a broken package rather than a broken
> toolchain pin.
>
> `create-app` already pins its choice in `package.json`'s `packageManager` field and Corepack honours
> it — that *is* the reproducibility guarantee. A second pin buys nothing and can only conflict. Fixed
> with `yarn set version stable` (4.4.1 → 4.18.0), which rewrites `yarnPath`, `packageManager` and
> `.yarn/releases/` together.
>
> To run `yarn set version` while the config is unreadable, comment the offending keys out first — the
> parse error blocks every Yarn command, including the one that fixes it.
>
> Keep the age gate rather than deleting it: it is [[supply-chain-choke-point]]'s argument applied to
> *time* rather than *location*. [[sonatype-nexus]] controls where a dependency comes from; the gate
> controls how battle-tested it is when you take it. `yarn add --no-time-gate` bypasses it for one
> command.

## Official docs

- What is Backstage: https://backstage.io/docs/overview/what-is-backstage
- Software templates: https://backstage.io/docs/features/software-templates/writing-templates
- Catalog entity descriptors: https://backstage.io/docs/features/software-catalog/descriptor-format
- Deploying with Docker: https://backstage.io/docs/deployment/docker
- Helm chart: https://github.com/backstage/charts

## Open questions

- Which discovery provider config would auto-register new `catalog-info.yaml` files in *one* repo?
- Is a GitHub App feasible without an inbound webhook URL on a laptop?

> [!tip] Related
> [[paved-paths]], [[argo-cd]], [[buildkite]], [[helm]], [[external-secrets-operator]], [[postgresql]]

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
- **Guest auth means there is no "who did that".** Every scaffolder run is attributed to one shared
  token. Production shape: GitHub OAuth for user identity plus a GitHub App so PRs are opened on
  behalf of the person who filled in the form.

## Gotchas

- Building the image in-cluster takes **20–40 minutes** with Buildah's `vfs` driver. Build on the host
  while iterating; let CI own it once stable.
- The bundled PostgreSQL uses a `bitnamilegacy` image — fine for a laptop, not for anything durable.
- New catalog files in an existing repo are **not** auto-discovered without a location entry or the
  GitHub discovery provider. This is the one seam the paved path leaves for a human (§14.7).

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

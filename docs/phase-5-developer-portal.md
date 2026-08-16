# Phase 5 — Making it someone else's platform

[← All phases](README.md) · [← Phase 4 — Identity between services](phase-4-service-mesh.md) · [Phase 6 — Operating it, and taking it down →](phase-6-operating.md)

> **Where this starts:** a platform only you know how to add a service to.
> **Where it ends:** a form that produces a reviewed pull request, which deploys itself.

Everything so far is a system. This phase is what turns it into a *product*: the test is not whether
you can add the next service, it is whether someone who has never read any of this can.

The measure of the paved paths here is what they **do not** require. No pipeline edit, no Deployment
written by hand, no Prometheus target registered, no ticket. Every one of those is a decision this
platform already made, encoded once, reviewed like code.

---

## 14. Backstage: paved paths, not documentation

### 14.1 What a portal is actually for

Everything up to here is a platform that one person can operate because that person built it. Hand it to a second engineer and the first question is "how do I add a service?", and the honest answer is currently "read fourteen sections of a tutorial". That answer does not scale, and the usual fix — a wiki page titled *How to add a service* — decays within two sprints because nothing breaks when it goes stale.

A **paved path** is that document made executable. The rule that makes it work:

> **The paved path must be the easiest path.** If the golden path is a form that produces a reviewed PR in ninety seconds, and the alternative is copying another service's directory and guessing, people take the form. If the paved path is slower than copy-paste, you have built a portal nobody uses and a wiki page with better formatting.

We use two parts of Backstage:

- **The catalog** — what exists, who owns it, what it depends on. Entities live in the repo next to the code, so ownership is reviewed like code.
- **The scaffolder** — templates that take a form and produce a change. Ours produce **pull requests against this repo**, never direct pushes to `main`. A paved path that bypasses review is not a path, it's a hole.

Two paved paths, matching the two things people ask for:

| Template | Produces | Reviewed by |
|---|---|---|
| **New service** | `services/<name>/` (code, Dockerfile, tests) + one chart file that deploys it | a PR |
| **New S3 bucket** | `deploy/platform/infra/<name>.yaml`, applied by Argo CD | a PR |

Both work because of decisions made earlier: CI discovers services from the filesystem ([§12.5](phase-3-delivery.md#125-the-pipeline)) and Argo CD recurses `deploy/platform` ([§11.4](phase-3-delivery.md#114-the-app-of-apps)). Neither template edits a pipeline, and neither touches the cluster.

> **Backstage is a framework, not a product.** You do not install Backstage; you *build* a Backstage. `create-app` scaffolds a TypeScript monorepo that is now your code, and adding a plugin means editing `packages/backend/src/index.ts` and rebuilding an image. That is the deal, and it is why we chose to build our own image rather than run the public demo one — the demo image's plugin set is fixed, and the first thing you'll want is a plugin it doesn't have.

### 14.2 First, an npm proxy in Nexus

A Backstage build pulls several thousand npm packages. Every one of them is a supply-chain event, and [§5.1](phase-0-foundations.md#51-what-nexus-is-actually-for) said the whole point of Nexus is that nothing enters this platform unproxied. So npm gets the same treatment PyPI and Go already have:

```bash
curl -u admin:admin123 -X POST 'http://localhost:8081/service/rest/v1/repositories/npm/proxy' \
  -H 'Content-Type: application/json' -d '{
    "name": "npm-proxy",
    "online": true,
    "storage": { "blobStoreName": "default", "strictContentTypeValidation": true },
    "proxy": { "remoteUrl": "https://registry.npmjs.org", "contentMaxAge": 1440, "metadataMaxAge": 1440 },
    "negativeCache": { "enabled": true, "timeToLive": 1440 },
    "httpClient": { "blocked": false, "autoBlock": true },
    "npm": { "removeNonCataloged": false }
  }'

curl -s -u admin:admin123 http://localhost:8081/service/rest/v1/repositories | jq -r '.[].name'
```

### 14.3 Scaffold the portal

Backstage needs an Active LTS Node. Let `create-app` choose the Yarn version — see the warning below:

```bash
brew install node@22
corepack enable

npx @backstage/create-app@latest --path portal
cd portal
```

> [!warning] **Do not `yarn set version` backwards here.**
> Earlier revisions of this tutorial ran `yarn set version 4.4.1` at this point. That downgrades Yarn
> below what `create-app@latest` generates, and the scaffold stops being able to read its own config:
>
> ```
> Usage Error: Unrecognized or legacy configuration settings found: npmMinimalAgeGate
> ```
>
> `create-app` writes supply-chain settings into `.yarnrc.yml` — `npmMinimalAgeGate` (refuse packages
> published less than N ago, Yarn **4.12+**) and `npmPreapprovedPackages` (exempt `@backstage/*` from
> it). Pinning 4.4.1 predates both. Nothing warns you at scaffold time; the failure arrives at the
> first `yarn add`.
>
> `create-app` already pins the version it wants in `package.json`'s `packageManager` field, and
> Corepack honours it — that *is* the reproducibility guarantee, so a second pin here buys nothing and
> can only conflict. If you do need to move it, move it **forwards**: `yarn set version stable`.
>
> The age gate is worth understanding rather than deleting: it is [§5.1](phase-0-foundations.md#51-what-nexus-is-actually-for)'s
> argument applied to time instead of location. Nexus controls *where* a dependency comes from; the
> gate controls *how battle-tested* it is when you take it. `yarn add --no-time-gate` bypasses it for
> one command when you genuinely need a fresh release.
```

Point it at Nexus rather than the public registry — the same choke point the services use:

**`portal/.yarnrc.yml`** (add to what `create-app` generated)

```yaml
npmRegistryServer: "http://nexus:8081/repository/npm-proxy/"
unsafeHttpWhitelist:
  - nexus
```

Add the scaffolder's GitHub actions. In the new backend system every provider's actions ship as their own module and none are on by default:

```bash
yarn --cwd packages/backend add @backstage/plugin-scaffolder-backend-module-github
```

**`portal/packages/backend/src/index.ts`** — add one line next to the other `backend.add(...)` calls:

```typescript
// Without this, `publish:github:pull-request` does not exist and every template
// run fails at the last step with "action not found" — after doing all the work.
backend.add(import('@backstage/plugin-scaffolder-backend-module-github'));
```

Check it boots locally before you think about containers:

```bash
yarn install
yarn start          # http://localhost:3000
```

### 14.4 Configure it for this platform

**`portal/app-config.production.yaml`**

```yaml
app:
  baseUrl: http://backstage.localtest.me

backend:
  baseUrl: http://backstage.localtest.me
  listen: ':7007'
  cors:
    origin: http://backstage.localtest.me
  database:
    client: pg
    connection:
      host: ${POSTGRES_HOST}
      port: ${POSTGRES_PORT}
      user: ${POSTGRES_USER}
      password: ${POSTGRES_PASSWORD}

integrations:
  github:
    - host: github.com
      # Fine-grained PAT, this repository only, Contents + Pull requests: RW.
      token: ${GITHUB_TOKEN}

auth:
  providers:
    guest:
      # Backstage refuses guest sign-in outside development unless you say this
      # out loud. Read §14.7 before you copy this line anywhere real.
      dangerouslyAllowOutsideDevelopment: true

catalog:
  rules:
    - allow: [Component, System, API, Resource, Location, Template, Group, User]
  locations:
    - type: url
      target: https://github.com/<your-github-user>/modern-devops/blob/main/catalog-info.yaml
    - type: url
      target: https://github.com/<your-github-user>/modern-devops/blob/main/deploy/backstage/templates/new-service/template.yaml
      rules: [{ allow: [Template] }]
    - type: url
      target: https://github.com/<your-github-user>/modern-devops/blob/main/deploy/backstage/templates/new-bucket/template.yaml
      rules: [{ allow: [Template] }]
```

> **`catalog.rules` is not boilerplate.** It is the allow-list of entity kinds a location may introduce. Without it, anyone who can open a PR to a catalogued repo can introduce a `Template` — and a Template is code that runs in your scaffolder with your GitHub token. The rules are why a catalog file is safe to accept from a service team and a template file is not.

### 14.5 Catalogue what already exists

The catalog is only as useful as it is complete, and it goes stale the moment it lives somewhere other than the code.

**`catalog-info.yaml`** (repo root)

```yaml
apiVersion: backstage.io/v1alpha1
kind: System
metadata:
  name: order-platform
  description: Order intake and persistence
spec:
  owner: group:default/platform
---
apiVersion: backstage.io/v1alpha1
kind: Component
metadata:
  name: order-api
  description: FastAPI order intake
  annotations:
    github.com/project-slug: <your-github-user>/modern-devops
spec:
  type: service
  lifecycle: production
  owner: group:default/platform
  system: order-platform
  providesApis: [orders]
---
apiVersion: backstage.io/v1alpha1
kind: Component
metadata:
  name: order-worker
  description: Go consumer, writes to S3 and DynamoDB
spec:
  type: service
  lifecycle: production
  owner: group:default/platform
  system: order-platform
  consumesApis: [orders]
  dependsOn: [resource:default/orders-raw]
---
apiVersion: backstage.io/v1alpha1
kind: Resource
metadata:
  name: orders-raw
  description: S3 bucket holding raw order payloads
spec:
  type: s3-bucket
  owner: group:default/platform
  system: order-platform
---
apiVersion: backstage.io/v1alpha1
kind: Group
metadata:
  name: platform
spec:
  type: team
  children: []
```

> **`dependsOn: [resource:default/orders-raw]` is the line that earns the catalog its keep.** When someone asks "what breaks if this bucket goes away", the answer is a query, not an archaeology project. Ownership and dependency edges are the only two pieces of catalog metadata that consistently pay for the effort of maintaining them; the rest is decoration until proven otherwise.

### 14.6 Paved path 1 — a new service

The template ships a skeleton and one chart file. Nothing else, because nothing else is needed: CI globs `services/*/Dockerfile` and the chart globs its own `services/*.yaml`.

**`deploy/backstage/templates/new-service/template.yaml`**

```yaml
apiVersion: scaffolder.backstage.io/v1beta3
kind: Template
metadata:
  name: new-service
  title: New service
  description: A Python service on the paved path — CI, image, deploy, metrics, mesh.
spec:
  owner: group:default/platform
  type: service

  parameters:
    - title: About the service
      required: [name, description, owner]
      properties:
        name:
          title: Name
          type: string
          description: Lowercase, hyphenated. Becomes the directory, image and workload name.
          pattern: '^[a-z][a-z0-9-]{2,29}$'
        description:
          title: What does it do?
          type: string
        owner:
          title: Owner
          type: string
          ui:field: OwnerPicker
          ui:options: { catalogFilter: { kind: Group } }
        exposePublicly:
          title: Route it from the ingress?
          type: boolean
          default: false

  steps:
    - id: fetch
      name: Render the skeleton
      action: fetch:template
      input:
        url: ./skeleton
        values:
          name: ${{ parameters.name }}
          description: ${{ parameters.description }}
          owner: ${{ parameters.owner }}
          exposePublicly: ${{ parameters.exposePublicly }}

    - id: pr
      name: Open a pull request
      action: publish:github:pull-request
      input:
        repoUrl: github.com?owner=<your-github-user>&repo=modern-devops
        branchName: paved-path/service-${{ parameters.name }}
        title: "feat(${{ parameters.name }}): new service via the paved path"
        description: |
          Generated by the **New service** template.

          - `services/${{ parameters.name }}/` — app, tests, Dockerfile
          - `deploy/charts/order-platform/services/${{ parameters.name }}.yaml` — how it deploys

          Merging this builds and deploys it. No pipeline or Argo CD changes are needed.

  output:
    links:
      - title: Review the pull request
        url: ${{ steps.pr.output.remoteUrl }}
```

The skeleton is ordinary files with `${{ values.x }}` placeholders. The two that matter:

**`deploy/backstage/templates/new-service/skeleton/deploy/charts/order-platform/services/${{ values.name }}.yaml`**

```yaml
# One file per scaffolded service. The chart globs this directory, so adding a
# service is a file creation, never an edit — which is what makes it a clean PR.
name: ${{ values.name }}
description: ${{ values.description }}
port: 8000
replicas: 1
ingress:
  enabled: ${{ values.exposePublicly }}
  host: ${{ values.name }}.localtest.me
```

**`deploy/backstage/templates/new-service/skeleton/services/${{ values.name }}/catalog-info.yaml`**

```yaml
apiVersion: backstage.io/v1alpha1
kind: Component
metadata:
  name: ${{ values.name }}
  description: ${{ values.description }}
spec:
  type: service
  lifecycle: experimental
  owner: ${{ values.owner }}
  system: order-platform
```

The rest of the skeleton lives in the repo at `deploy/backstage/templates/new-service/skeleton/services/${{ values.name }}/`:

```
app/__init__.py     app/main.py     app/settings.py
tests/__init__.py   tests/test_api.py
pyproject.toml      uv.lock         Dockerfile      .python-version
```

The `Dockerfile` is a straight copy of order-api's, deliberately — a paved path that builds differently from the service it was modelled on stops being a paved path the first time someone debugs it. The rest is order-api with the parts a *new* service doesn't have removed: no Kafka producer, no S3 client, no signing key. What survives is the contract the chart depends on — `/healthz`, `/readyz`, `/metrics` on port 8000 — plus one placeholder route so the service does something observable on day one.

> **Three things in here are not a mechanical copy, and each one is a trap avoided.**
>
> **`uv.lock` is templated too.** Skipping it and dropping `--locked` from the skeleton's Dockerfile would silently give every scaffolded service worse reproducibility than the two hand-written ones — a paved path that is *worse* than the manual route is how paved paths die. It works because the project name appears in `uv.lock` exactly once:
> ```toml
> [[package]]
> name = "${{ values.name }}"
> version = "0.1.0"
> source = { editable = "." }
> ```
> The scaffolder substitutes it in the lock and in `pyproject.toml` together, so they still agree. Generate it once by rendering the skeleton under any name, running `uv lock`, and replacing that one name with the placeholder on the way back.
>
> **`pyproject.toml` carries the Nexus index.** `[[tool.uv.index]]` again, for the reason in [§3.1](phase-1-the-application.md#31-order-api-python--fastapi): an index set only in CI can never match a committed lock. Omit it and every scaffolded service quietly resolves from `pypi.org`, straight through the choke point [§5.1](phase-0-foundations.md#51-what-nexus-is-actually-for) exists to close — and nothing fails to tell you.
>
> **The metric prefix is computed in Python, not templated.** Service names are hyphenated (`quotes-api`); Prometheus metric names may not be. So `main.py` does `SERVICE.replace("-", "_")` rather than emitting `quotes-api_requests_total`, which would be rejected at registration. Doing it in code instead of in the scaffolder means a rename can never produce an invalid metric name, and there's a test asserting exactly that.

For the chart to render these files, add one template that reads the directory:

**`deploy/charts/order-platform/templates/scaffolded.yaml`**

```yaml
{{- range $path, $_ := .Files.Glob "services/*.yaml" }}
{{- $svc := $.Files.Get $path | fromYaml }}
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: {{ $svc.name }}
  labels: {{- include "op.labels" (dict "name" $svc.name "root" $) | nindent 4 }}
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ $svc.name }}
  labels: {{- include "op.labels" (dict "name" $svc.name "root" $) | nindent 4 }}
spec:
  replicas: {{ $svc.replicas | default 1 }}
  selector:
    matchLabels:
      app.kubernetes.io/name: {{ $svc.name }}
  template:
    metadata:
      labels: {{- include "op.labels" (dict "name" $svc.name "root" $) | nindent 8 }}
      annotations:
        prometheus.io/scrape: "true"
        prometheus.io/path: "/metrics"
        prometheus.io/port: {{ $svc.port | quote }}
    spec:
      serviceAccountName: {{ $svc.name }}
      imagePullSecrets:
        - name: {{ $.Values.global.imagePullSecret }}
      securityContext:
        runAsNonRoot: true
        seccompProfile: { type: RuntimeDefault }
      containers:
        - name: {{ $svc.name }}
          # Every scaffolded service is built from the same commit, so they all
          # carry the same tag. CI writes it once, in deploy/env/local/values.yaml.
          image: "{{ $.Values.global.registry }}/shop/{{ $svc.name }}:{{ $.Values.scaffolded.tag }}"
          ports:
            - { name: http, containerPort: {{ $svc.port }} }
          env:
            {{- include "op.commonEnv" $ | nindent 12 }}
          readinessProbe:
            httpGet: { path: /readyz, port: http }
          resources:
            requests: { cpu: 50m, memory: 128Mi }
            limits:   { memory: 256Mi }
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities: { drop: ["ALL"] }
---
apiVersion: v1
kind: Service
metadata:
  name: {{ $svc.name }}
  labels: {{- include "op.labels" (dict "name" $svc.name "root" $) | nindent 4 }}
spec:
  selector:
    app.kubernetes.io/name: {{ $svc.name }}
  ports:
    - { name: http, port: 80, targetPort: http }
{{- if $svc.ingress.enabled }}
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: {{ $svc.name }}
spec:
  ingressClassName: nginx
  rules:
    - host: {{ $svc.ingress.host }}
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: {{ $svc.name }}
                port: { name: http }
{{- end }}
{{- end }}
```

Add the default the template references, in **`deploy/charts/order-platform/values.yaml`**:

```yaml
scaffolded:
  tag: "dev"     # CI overwrites this in the env overlay, same as the other two
```

> **`.Files.Glob` is doing something subtle and worth naming.** A chart normally takes its input from `values.yaml`, which means onboarding a service is an *edit* to a shared file — merge conflicts when two teams onboard the same week, and a diff that reviewers have to read carefully. Reading a directory instead turns onboarding into a file *creation*: conflict-free, trivially reviewable, and trivially revertible. When you design a paved path, bias every step towards adding a file rather than editing one.

> **What this deliberately does not template.** No per-service Kafka topic, no per-service secret, no autoscaling. A paved path earns trust by being narrow and predictable; the moment it grows a checkbox for everything, it becomes a worse version of writing the YAML by hand. Services that need more than the path provides should fall off it deliberately and copy the chart's explicit `order-api.yaml` instead.

### 14.7 Paved path 2 — infrastructure

Same shape, different artifact: a form produces a manifest that Argo CD applies.

**`deploy/backstage/templates/new-bucket/template.yaml`**

```yaml
apiVersion: scaffolder.backstage.io/v1beta3
kind: Template
metadata:
  name: new-bucket
  title: New S3 bucket
  description: An S3 bucket, created by GitOps and owned by a team.
spec:
  owner: group:default/platform
  type: resource

  parameters:
    - title: About the bucket
      required: [bucketName, owner]
      properties:
        bucketName:
          title: Bucket name
          type: string
          pattern: '^[a-z0-9][a-z0-9-]{2,62}$'
        owner:
          title: Owner
          type: string
          ui:field: OwnerPicker
          ui:options: { catalogFilter: { kind: Group } }

  steps:
    - id: fetch
      name: Render the manifest
      action: fetch:template
      input:
        url: ./skeleton
        values:
          bucketName: ${{ parameters.bucketName }}
          owner: ${{ parameters.owner }}

    - id: pr
      name: Open a pull request
      action: publish:github:pull-request
      input:
        repoUrl: github.com?owner=<your-github-user>&repo=modern-devops
        branchName: paved-path/bucket-${{ parameters.bucketName }}
        title: "feat(infra): s3 bucket ${{ parameters.bucketName }}"
        description: |
          Creates the `${{ parameters.bucketName }}` bucket. Argo CD applies it on merge.

  output:
    links:
      - title: Review the pull request
        url: ${{ steps.pr.output.remoteUrl }}
```

**`deploy/backstage/templates/new-bucket/skeleton/deploy/platform/infra/${{ values.bucketName }}.yaml`**

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: create-bucket-${{ values.bucketName }}
  namespace: floci
  annotations:
    # Argo CD re-runs this whenever the manifest changes; the command is
    # idempotent, so a re-run is a no-op rather than an error.
    argocd.argoproj.io/hook: Sync
spec:
  backoffLimit: 6
  ttlSecondsAfterFinished: 600
  template:
    metadata:
      annotations:
        sidecar.istio.io/inject: "false"   # §9.3: Jobs and sidecars don't mix
    spec:
      restartPolicy: OnFailure
      containers:
        - name: awscli
          image: amazon/aws-cli:2.32.9
          env:
            - { name: AWS_ENDPOINT_URL,      value: "http://floci.floci.svc.cluster.local:4566" }
            - { name: AWS_DEFAULT_REGION,    value: "us-east-1" }
            - { name: AWS_ACCESS_KEY_ID,     value: "test" }
            - { name: AWS_SECRET_ACCESS_KEY, value: "test" }
          command: ["/bin/sh", "-c"]
          args:
            - |
              set -eu
              aws s3api create-bucket --bucket ${{ values.bucketName }} 2>/dev/null \
                || echo "bucket already exists"
              aws s3api head-bucket --bucket ${{ values.bucketName }}
              echo "owner: ${{ values.owner }}"
```

> **A Job is not a control loop, and you should feel the difference.** This creates the bucket and stops. It will not notice if someone deletes it, it cannot express "make the bucket look like this", and there is no drift detection — the manifest in git can be a lie ten minutes after it merges. The production answer is a provider that reconciles: **Crossplane** or the **AWS Controllers for Kubernetes**, where an `S3Bucket` custom resource is continuously reconciled against the real thing. That's another operator and another CRD set, which is why it isn't here. If you take one idea from this section into a real platform, take that one: **paved paths should produce declarative resources, not one-shot jobs.**

> **The seam, stated plainly.** The bucket appears in the cluster but not in the catalog. Backstage discovers catalog files from *configured locations*, and a brand-new file in an existing repo is not one until either someone adds a location entry or you enable the GitHub discovery provider (`@backstage/plugin-catalog-backend-module-github`) to scan the repo. Until then, add the `Resource` entity to the root `catalog-info.yaml` by hand in the same PR. We're not pretending otherwise: this is the one place where our paved path still needs a human to do a second thing.

### 14.8 Build and deploy the portal

The portal is built by our own CI, on the same path as everything else — it's just a bigger image. It needs a Dockerfile CI can actually run (see the warning below for why the generated one will not do), and a build step in the generator:

**`portal/Dockerfile`** — Backstage's [multi-stage build](https://backstage.io/docs/deployment/docker#multi-stage-build), which compiles the project *inside* the image. This is the one CI uses; see the warning below for why the generated `packages/backend/Dockerfile` cannot be.

```dockerfile
# Multi-stage build, from https://backstage.io/docs/deployment/docker#multi-stage-build
#
# This exists alongside packages/backend/Dockerfile, which create-app generates
# and which is a *host build*: it expects `yarn install && yarn tsc &&
# yarn build:backend` to have already produced packages/backend/dist/. That is
# fine on a laptop and impossible in our CI, where the build step is a Buildah
# pod with no Node toolchain. This one builds the project inside the image, so
# `buildah bud` against the portal directory is self-contained.
#
# Slower than a host build. That is the trade for not needing Node in CI.

# Stage 1 - Create yarn install skeleton layer
FROM docker.io/library/node:24-trixie-slim AS packages

WORKDIR /app
COPY backstage.json package.json yarn.lock ./
COPY .yarn ./.yarn
COPY .yarnrc.yml ./

COPY packages packages

# No internal plugins in this portal — portal/plugins/ holds only a README, and
# .dockerignore excludes it, so this COPY matches nothing and fails the build.
# Uncomment it the day you add one.
# COPY plugins plugins

RUN find packages \! -name "package.json" -mindepth 2 -maxdepth 2 -exec rm -rf {} \+

# Stage 2 - Install dependencies and build packages
FROM docker.io/library/node:24-trixie-slim AS build

# Set Python interpreter for `node-gyp` to use
ENV PYTHON=/usr/bin/python3

# Install isolate-vm dependencies, these are needed by the @backstage/plugin-scaffolder-backend.
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && \
    apt-get install -y --no-install-recommends python3 g++ build-essential && \
    rm -rf /var/lib/apt/lists/*

# Install sqlite3 dependencies. You can skip this if you don't use sqlite3 in the image,
# in which case you should also move better-sqlite3 to "devDependencies" in package.json.
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && \
    apt-get install -y --no-install-recommends libsqlite3-dev && \
    rm -rf /var/lib/apt/lists/*

USER node
WORKDIR /app

COPY --from=packages --chown=node:node /app .

# .yarnrc.yml points npmRegistryServer at Nexus, so this resolves through the
# choke point (§5.1) exactly like pip and Go do — the build pod's DNS reaches
# `nexus` the same way every other pod does.
RUN --mount=type=cache,target=/home/node/.cache/yarn,sharing=locked,uid=1000,gid=1000 \
    yarn install --immutable

COPY --chown=node:node . .

RUN yarn tsc
RUN yarn --cwd packages/backend build

RUN mkdir packages/backend/dist/skeleton packages/backend/dist/bundle \
    && tar xzf packages/backend/dist/skeleton.tar.gz -C packages/backend/dist/skeleton \
    && tar xzf packages/backend/dist/bundle.tar.gz -C packages/backend/dist/bundle

# Stage 3 - Build the actual backend image and install production dependencies
FROM docker.io/library/node:24-trixie-slim

# Set Python interpreter for `node-gyp` to use
ENV PYTHON=/usr/bin/python3

# Install isolate-vm dependencies, these are needed by the @backstage/plugin-scaffolder-backend.
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && \
    apt-get install -y --no-install-recommends python3 g++ build-essential && \
    rm -rf /var/lib/apt/lists/*

# Install sqlite3 dependencies. You can skip this if you don't use sqlite3 in the image,
# in which case you should also move better-sqlite3 to "devDependencies" in package.json.
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && \
    apt-get install -y --no-install-recommends libsqlite3-dev && \
    rm -rf /var/lib/apt/lists/*

# From here on we use the least-privileged `node` user to run the backend.
USER node

# This should create the app dir as `node`.
# If it is instead created as `root` then the `tar` command below will
# fail: `can't create directory 'packages/': Permission denied`.
# If this occurs, then ensure BuildKit is enabled (`DOCKER_BUILDKIT=1`)
# so the app dir is correctly created as `node`.
WORKDIR /app

# Copy the install dependencies from the build stage and context
COPY --from=build --chown=node:node /app/.yarn ./.yarn
COPY --from=build --chown=node:node /app/.yarnrc.yml  ./
COPY --from=build --chown=node:node /app/backstage.json ./
COPY --from=build --chown=node:node /app/yarn.lock /app/package.json /app/packages/backend/dist/skeleton/ ./

# Note: The skeleton bundle only includes package.json files -- if your app has
# plugins that define a `bin` export, the bin files need to be copied as well to
# be linked in node_modules/.bin during yarn install.

RUN --mount=type=cache,target=/home/node/.cache/yarn,sharing=locked,uid=1000,gid=1000 \
    yarn workspaces focus --all --production && rm -rf "$(yarn cache clean)"

# Copy the built packages from the build stage
COPY --from=build --chown=node:node /app/packages/backend/dist/bundle/ ./

# Copy any other files that we need at runtime
COPY --chown=node:node app-config*.yaml ./

# This will include the examples, if you don't need these simply remove this line
COPY --chown=node:node examples ./examples

# This switches many Node.js dependencies to production mode.
ENV NODE_ENV=production

# This disables node snapshot for Node 20 to work with the Scaffolder
ENV NODE_OPTIONS="--no-node-snapshot"

CMD ["node", "packages/backend", "--config", "app-config.yaml", "--config", "app-config.production.yaml"]
```

`create-app` also writes a `.dockerignore` tuned for the *host* build, and one line in it is fatal to the multi-stage one:

**`portal/.dockerignore`**

```
.git
.yarn/cache
.yarn/install-state.gz
node_modules
# NOT excluded: portal/Dockerfile is a multi-stage build that compiles from
# source inside the image, so `yarn tsc` needs packages/*/src. create-app writes
# this file for the *host* build, where dist/ is prebuilt and the sources are
# dead weight. Excluding them fails with TS18003 "No inputs were found in config
# file", which names tsconfig.json and never mentions Docker.
# packages/*/src
packages/*/node_modules
plugins
*.local.yaml
```

> **`packages/*/src` must not be excluded.** For a host build the TypeScript sources are dead weight — `dist/` is already compiled, so excluding them just makes the context smaller. The multi-stage build compiles *from* those sources, and without them `yarn tsc` fails with:
>
> ```
> error TS18003: No inputs were found in config file '/app/tsconfig.json'.
> Specified 'include' paths were '["packages/*/src", ...]'
> ```
>
> Which names `tsconfig.json` and never mentions Docker, so it sends you into TypeScript config rather than at what you copied into the build context. `plugins` stays excluded, because the `COPY plugins plugins` line is commented out above.

**`.buildkite/pipeline.sh`** — after the services loop, before the deploy step:

```sh
# The portal is not a service and does not fit the services template: a
# different Dockerfile path, a different context, and a build measured in
# double-digit minutes.
cat <<YAML

  - label: ":backstage: build portal ($SHA)"
    key: build-portal
    branches: "main"
    agents: { queue: kubernetes }
    timeout_in_minutes: 45
    plugins:
      - kubernetes:
          podSpec:
            volumes:
              - name: nexus-auth
                secret: { secretName: nexus-push }
            containers:
              - image: quay.io/buildah/stable:v1.40.1
                securityContext:
                  privileged: true
                env:
                  - name: STORAGE_DRIVER
                    value: vfs
                  - name: BUILDAH_FORMAT
                    value: docker
                  - name: REGISTRY_AUTH_FILE
                    value: /auth/config.json
                volumeMounts:
                  - name: nexus-auth
                    mountPath: /auth
                    readOnly: true
                command:
                  - |
                    set -euo pipefail
                    buildah bud \\
                      --tls-verify=false \\
                      --file portal/Dockerfile \\
                      --tag "$REGISTRY/shop/portal:$SHA" \\
                      portal

                    buildah push --tls-verify=false "$REGISTRY/shop/portal:$SHA"
YAML
```

> **Twenty to forty minutes, in a `vfs`-backed privileged pod, on your laptop.** That is the honest cost of building Backstage in-cluster, and `vfs` (which we chose in §12.5 because overlay-in-overlay needs privileges we'd rather not grant) is most of it. Two mitigations worth knowing: `branches: "main"` keeps it off every branch build, and while you are iterating on the portal you should build it on the host and let CI own it only once it's stable. Waiting is not a lesson. On the host, use the Dockerfile `create-app` generated — but note that it is a **host build** and needs the project compiled first:

```bash
cd portal
yarn install --immutable
yarn tsc
yarn build:backend          # produces packages/backend/dist/{skeleton,bundle}.tar.gz
cd ..
docker build -f portal/packages/backend/Dockerfile -t nexus:8082/shop/portal:dev portal
docker push nexus:8082/shop/portal:dev
```

> [!warning] **Two Dockerfiles, and CI must use the right one.**
> `create-app` generates `portal/packages/backend/Dockerfile`, whose own header says:
>
> ```
> # Before building this image, be sure to have run the following commands in the repo root:
> #   yarn install --immutable
> #   yarn tsc
> #   yarn build:backend
> ```
>
> It is a **host build**: it only *copies* `packages/backend/dist/skeleton.tar.gz`, it does not create
> it. Our CI step is a Buildah pod with no Node toolchain, so pointing it at that file fails after a
> couple of minutes of pulling base layers:
>
> ```
> STEP 12/18: COPY --chown=node:node yarn.lock package.json packages/backend/dist/skeleton.tar.gz ./
> Error: ... copier: stat: "/packages/backend/dist/skeleton.tar.gz": no such file or directory
> exit status 125
> ```
>
> That is why `portal/Dockerfile` exists: Backstage's documented
> [multi-stage build](https://backstage.io/docs/deployment/docker#multi-stage-build), which compiles
> the project *inside* the image and is therefore self-contained. Three stages — a skeleton layer of
> nothing but `package.json` files so dependency installs cache, a build stage that runs the same
> `yarn tsc` / `yarn build` you would run by hand, and a production stage carrying only the bundle and
> production dependencies. It resolves npm through Nexus because `.yarnrc.yml` is copied in before
> `yarn install`, so the [§14.2](#142-first-an-npm-proxy-in-nexus) proxy applies to the container
> build too.
>
> Keep both. The host build is faster while you iterate; the multi-stage one is what CI can actually
> run.

Backstage needs a database and a GitHub token. The token comes from OpenBao through ESO, exactly like every other secret ([§7.6](phase-1-the-application.md#76-let-kubernetes-pull-from-nexus)):

```bash
kubectl create namespace backstage

kubectl -n openbao exec -it openbao-0 -- sh -c '
  export BAO_ADDR=http://127.0.0.1:8200
  bao kv put shop/backstage github_token="<your-fine-grained-PAT>"'
```

**`deploy/platform/backstage-secrets.yaml`**

```yaml
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: backstage
  namespace: backstage
spec:
  refreshInterval: "1h"
  secretStoreRef:
    name: openbao
    kind: ClusterSecretStore
  target:
    name: backstage
    creationPolicy: Owner
  data:
    - secretKey: GITHUB_TOKEN
      remoteRef: { key: backstage, property: github_token }
---
# The portal is pulled from Nexus like everything else, so the `backstage`
# namespace needs its own pull secret. Secrets do not cross namespaces — §7's
# `nexus-pull` lives in `shop` and is invisible here. Without this the kubelet
# reports `no basic auth credentials`, which reads like a registry problem and
# is really a missing Secret in this namespace.
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: nexus-pull
  namespace: backstage
spec:
  refreshInterval: "1h"
  secretStoreRef:
    name: openbao
    kind: ClusterSecretStore
  target:
    name: nexus-pull
    creationPolicy: Owner
    template:
      type: kubernetes.io/dockerconfigjson
      data:
        .dockerconfigjson: |
          {
            "auths": {
              "nexus:8082": {
                "username": "{{ .username }}",
                "password": "{{ .password }}",
                "auth": "{{ printf "%s:%s" .username .password | b64enc }}"
              }
            }
          }
  data:
    - secretKey: username
      remoteRef: { key: nexus, property: username }
    - secretKey: password
      remoteRef: { key: nexus, property: password }
```

**`infra/backstage-values.yaml`**

```yaml
backstage:
  image:
    registry: nexus:8082
    # Set this to the SHA your CI pushed. Nothing rewrites it for you — see the
    # note below.
    repository: shop/portal
    tag: "dev"
    # Secrets do not cross namespaces: §7's nexus-pull lives in `shop`, so the
    # backstage namespace needs its own (created by backstage-secrets.yaml).
    # Without this the kubelet says `no basic auth credentials`.
    pullSecrets:
      - nexus-pull
  extraEnvVarsSecrets:
    - backstage

ingress:
  enabled: true
  className: nginx
  host: backstage.localtest.me

postgresql:
  enabled: true
  auth:
    username: bn_backstage
    password: backstage-change-me
```

> [!warning] **Do not set `POSTGRES_*` in `extraEnvVars` — the chart already does.**
> With `postgresql.enabled: true` the chart wires the backend to its own Postgres subchart, emitting
> exactly the four variables it needs. Adding them again by hand produces a Deployment with each key
> twice, and the install dies before anything is created:
>
> ```
> Error: server-side apply failed for object backstage/backstage apps/v1, Kind=Deployment:
>   .spec.template.spec.containers[name="backstage-backend"].env:
>     duplicate entries for key [name="POSTGRES_HOST"]
>     ... POSTGRES_PORT, POSTGRES_USER, POSTGRES_PASSWORD
> ```
>
> Server-side apply treats `env` as a list keyed by `name` and **rejects duplicate keys outright**.
> Client-side apply silently kept the last one, which is why this pattern survived in a lot of
> older values files — the strictness is new, and it is an improvement: two entries for the same
> variable is always a bug, it just used to be a *silent* one.
>
> The values the chart generates are identical to the ones being added here, so deleting the block
> changes nothing about the running pod. Keep `extraEnvVarsSecrets`, which is what injects
> `GITHUB_TOKEN` from [§14.8](#148-build-and-deploy-the-portal).
>
> If you point Backstage at a database you control (`postgresql.enabled: false`), then you **do** set
> `POSTGRES_*` yourself — that is the case `extraEnvVars` exists for, and there is no duplicate
> because the chart contributes nothing.

```bash
helm repo add backstage https://backstage.github.io/charts
helm repo update

kubectl apply -f deploy/platform/backstage-secrets.yaml

helm upgrade --install backstage backstage/backstage \
  --namespace backstage --version 2.10.0 \
  --values infra/backstage-values.yaml --wait
```

Open <http://backstage.localtest.me>, sign in as Guest, and you should see the catalogue from §14.5 and both templates under **Create**.

> **You just went back to deploying by hand, and you should notice.**
> [Phase 1](phase-1-the-application.md#105-install-it) installed the application with `helm install`
> from your laptop. [Phase 3](phase-3-delivery.md#114-the-app-of-apps) took that away and made git the
> deploy button. And here you are, three phases later, typing `helm upgrade --install` again with a
> tag you set by hand — for the one component whose entire job is paving paths for other people.
>
> That is not an oversight, it is the exercise: making the portal an Argo CD `Application` and
> teaching CI to bump its tag is [§11.4](phase-3-delivery.md#114-the-app-of-apps) and
> [§12.5](phase-3-delivery.md#125-the-pipeline) applied one more time, and doing it yourself is a far
> better test of whether Phase 3 landed than reading a third worked example. Notice the irony while
> you're at it — **the tool whose whole purpose is paving paths is currently the least paved thing in
> the cluster.** That is also how platform teams usually look from the outside.

> **The portal is the one thing here still deployed by `helm install` from your laptop** — imperatively, outside GitOps, with a tag you set by hand. That is a deliberate stopping point, not an oversight: making it an Argo CD `Application` and teaching CI to bump its tag is exactly the work of [§11.4](phase-3-delivery.md#114-the-app-of-apps) and [§12.5](phase-3-delivery.md#125-the-pipeline) applied one more time, and doing it yourself is a better test of whether those two sections landed than reading a third worked example. Note the irony while you're at it — **the tool whose entire job is paving paths for other people is, right now, the least paved thing in the cluster.** That is how platforms usually look.

> **Guest sign-in means there is no such thing as "who did that".** Every scaffolder run, every PR the portal opens, is attributed to the one GitHub token — so the audit trail says "the portal did it" and stops. That is tolerable on a laptop and indefensible anywhere else, because the portal's token is more privileged than any individual's. The production shape is GitHub OAuth for user identity plus the scaffolder acting as a GitHub App, so the PR is opened *on behalf of* the person who filled in the form. Wire that up before a second person uses your portal, not after.

> **The bundled PostgreSQL is a `bitnamilegacy` image, and that's a smell worth tracking.** Bitnami's catalogue changes broke a lot of charts in 2025 and the Backstage chart's default now points at the legacy registry. It works, and for a laptop it is fine. For anything durable, run Postgres you actually control — an operator, or a managed database — and set `postgresql.enabled: false` with `POSTGRES_*` pointing at it. **Never let your portal's database be the least-maintained component in your platform**, because when it dies you lose the catalog, and the catalog is what you'd have used to find out what depends on it.

```bash
git add portal catalog-info.yaml deploy/backstage deploy/platform/backstage-secrets.yaml \
        deploy/charts/order-platform infra/backstage-values.yaml .buildkite/pipeline.sh
git commit -m "feat(portal): backstage with service and infrastructure paved paths"
git push
```

---

## Where you are

Someone who has read none of this can add a service to your platform through a form, get a pull
request they can review, and have it built, deployed, meshed and monitored on merge — because every
one of those decisions was made once, here, by you.

**Next: [Phase 6 — Operating it](phase-6-operating.md).** Now find out what happens when it breaks.

[← All phases](README.md) · [← Phase 4 — Identity between services](phase-4-service-mesh.md) · [Phase 6 — Operating it, and taking it down →](phase-6-operating.md)

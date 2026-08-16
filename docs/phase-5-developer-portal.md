# Phase 5 — Making it someone else's platform

[← All phases](README.md) · [← Phase 4 — Identity between services](phase-4-service-mesh.md) · [Phase 7 — One build system, many languages →](phase-7-polyglot-monorepo.md)

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

Backstage needs an Active LTS Node. Let `create-app` choose the Yarn version:

```bash
brew install node@22
corepack enable

npx @backstage/create-app@latest --path portal
cd portal
```

> **Do not run `yarn set version` here.** `create-app` pins the version it wants in `package.json`'s
> `packageManager` field and Corepack honours it, so a second pin buys nothing and an older one makes
> the scaffold unable to read the `.yarnrc.yml` it just wrote. If you ever need to move it, move it
> **forwards**: `yarn set version stable`.

Two of the settings `create-app` writes into `.yarnrc.yml` are worth knowing rather than deleting:
`npmMinimalAgeGate` refuses packages published less recently than the given window, and
`npmPreapprovedPackages` exempts `@backstage/*` from it. That is
[§5.1](phase-0-foundations.md#51-what-nexus-is-actually-for)'s argument applied to time instead of
location — Nexus controls *where* a dependency comes from, the gate controls *how battle-tested* it is
when you take it. `yarn add --no-time-gate` bypasses it for one command when you genuinely need a fresh
release.

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

Replace `<your-github-user>` with the account your fork of this repo lives under, here and everywhere
else it appears in this phase. The URLs are `https`, not `http`: the Backstage frontend calls
`crypto.randomUUID`, which the browser only exposes in a secure context, so the portal is served over
TLS at the edge and every URL it knows about itself has to agree ([§14.8](#148-build-and-deploy-the-portal)).

**`portal/app-config.production.yaml`**

```yaml
app:
  baseUrl: https://backstage.localtest.me

backend:
  baseUrl: https://backstage.localtest.me
  listen:
    # Object form. The string shorthand (`listen: ':7007'`) is rejected:
    #   Invalid type in config for key 'backend.listen', got string, wanted object
    # host must be 0.0.0.0, not the 127.0.0.1 default, or the container binds to
    # loopback and the kubelet's probes never reach it.
    host: 0.0.0.0
    port: 7007
  cors:
    origin: https://backstage.localtest.me
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
      # out loud. Read the end of §14.8 before you copy this line anywhere real.
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
  description: FastAPI order intake; prices every order over gRPC before accepting it
  annotations:
    github.com/project-slug: <your-github-user>/modern-devops
spec:
  type: service
  lifecycle: production
  owner: group:default/platform
  system: order-platform
  providesApis: [orders]
  consumesApis: [pricing]
  dependsOn: [component:default/pricing]
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
kind: Component
metadata:
  name: pricing
  description: >-
    gRPC pricing service. Runs as two versions behind one Kubernetes Service so
    Istio can shift traffic between them; the version that answered is returned
    to the caller as `served_by` (§18).
  annotations:
    github.com/project-slug: <your-github-user>/modern-devops
spec:
  type: service
  lifecycle: production
  owner: group:default/platform
  system: order-platform
  providesApis: [pricing]
---
apiVersion: backstage.io/v1alpha1
kind: Component
metadata:
  name: frontend
  description: >-
    Canary Watch — the Vite dashboard that tallies `served_by` across repeated
    orders, so a traffic shift is something you watch rather than something you
    read out of a metric (§19).
  annotations:
    github.com/project-slug: <your-github-user>/modern-devops
spec:
  type: website
  lifecycle: production
  owner: group:default/platform
  system: order-platform
  consumesApis: [orders]
---
apiVersion: backstage.io/v1alpha1
kind: API
metadata:
  name: orders
  description: The REST surface order-api exposes at the edge
spec:
  type: openapi
  lifecycle: production
  owner: group:default/platform
  system: order-platform
  # Generated, never hand-written — `pants run services/order-api:dump-openapi`.
  # A drift test fails the build if this file stops matching the routes, because
  # a stale spec the portal keeps rendering is worse than no spec at all.
  definition:
    $text: ./services/order-api/openapi.json
---
apiVersion: backstage.io/v1alpha1
kind: API
metadata:
  name: pricing
  description: The gRPC contract between order-api and pricing
spec:
  type: grpc
  lifecycle: production
  owner: group:default/platform
  system: order-platform
  # The .proto is the contract itself, and Pants compiles this exact file into
  # both the Python server and the Go stubs (§17.4). There is no second copy to
  # drift from.
  definition:
    $text: ./protos/shop/v1/pricing.proto
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

> **`definition.$text` points at the generated artefact, never a copy.** The OpenAPI JSON is emitted
> from the routes and the `.proto` *is* the gRPC contract, so what the portal renders cannot drift from
> what the services actually speak. An API entity whose definition is a hand-maintained second copy is
> worse than no API entity at all.

> **`dependsOn: [resource:default/orders-raw]` is the line that earns the catalog its keep.** When someone asks "what breaks if this bucket goes away", the answer is a query, not an archaeology project. Ownership and dependency edges are the only two pieces of catalog metadata that consistently pay for the effort of maintaining them; the rest is decoration until proven otherwise.

### 14.6 Paved path 1 — a new service

The template ships a skeleton and one chart file. Nothing else, because nothing else is needed: CI discovers any `services/*` directory holding both a `BUILD` and a `Dockerfile`, and the chart globs its own `services/*.yaml`.

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

The skeleton is ordinary files with `${{ values.x }}` placeholders. Start with the two that wire a new service into the platform — how it deploys, and who owns it:

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
${{ values.name | replace('-', '_') }}/__init__.py   … /main.py   … /settings.py
tests/__init__.py   tests/test_api.py
BUILD               Dockerfile
```

Name the package directory `${{ values.name | replace('-', '_') }}`, not `app`. Every service under the
`services/*` source root that declares a top-level `app` package collides with every other one, so
templating the directory makes each scaffolded package name unique by construction — see
[§17.4](phase-7-polyglot-monorepo.md#174-source-roots-and-the-duplicate-module-trap).

**`deploy/backstage/templates/new-service/skeleton/services/${{ values.name }}/BUILD`**

```python
# A scaffolded service is a first-class member of the Pants monorepo. Without
# this file CI would not build it at all — service discovery in
# .buildkite/pipeline.sh keys off services/*/BUILD, and a directory Pants does
# not know about cannot be linted, typechecked, tested or packaged. The failure
# would be silent: the pipeline would simply not mention the new service.
python_sources(
    name="lib",
    sources=["${{ values.name | replace('-', '_') }}/**/*.py"],
)

python_tests(
    name="tests",
    sources=["tests/**/*.py", "!tests/__init__.py"],
    # Explicit because several services could otherwise satisfy this import.
    dependencies=[":lib"],
)

pex_binary(
    name="bin",
    entry_point="${{ values.name | replace('-', '_') }}.main:main",
    dependencies=[":lib"],
    # The cluster runs linux/arm64. Without this, a PEX built on a macOS
    # laptop resolves macOS wheels, passes every check, and dies on import
    # inside the container. See 3rdparty/python/BUILD.
    complete_platforms=["3rdparty/python:linux-platform"],
    # dist/ is the Buildah build context; the Dockerfile COPYs by this name.
    output_path="${{ values.name }}.pex",
)
```

**`deploy/backstage/templates/new-service/skeleton/services/${{ values.name }}/Dockerfile`**

```dockerfile
# syntax=docker/dockerfile:1.7
#
# Build context is `dist/` — the output of `pants package`, not this source
# tree. The PEX already carries the whole dependency closure resolved from
# locks/python-default.lock, so there is nothing for this image to install.
FROM docker.io/library/python:3.13-slim

RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin appuser

WORKDIR /app
COPY --chown=10001:10001 ${{ values.name }}.pex /app/service.pex

# A PEX unpacks its dependency closure on first run, so it needs somewhere
# writable. Under readOnlyRootFilesystem it has nowhere and dies in the PEX
# bootstrap before any application log line appears. The chart mounts an
# emptyDir at /tmp to match.
ENV PEX_ROOT=/tmp/pex \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER 10001
EXPOSE 8000
ENTRYPOINT ["python", "/app/service.pex"]
```

The `Dockerfile` is the same four-line shape order-api's has, deliberately — a paved path that builds differently from the services it was modelled on stops being a paved path the first time someone debugs it. There is no `pyproject.toml` and no per-service lock: dependency resolution is the monorepo's job ([§17](phase-7-polyglot-monorepo.md)), which is also what keeps a scaffolded service resolving through Nexus rather than `pypi.org` without the template having to say so. The Python is order-api with the parts a *new* service doesn't have removed: no Kafka producer, no S3 client, no signing key. What survives is the contract the chart depends on — `/healthz`, `/readyz`, `/metrics` on port 8000 — plus one placeholder route so the service does something observable on day one.

> **The metric prefix is computed in Python, not templated.** Service names are hyphenated (`quotes-api`); Prometheus metric names may not be. So `main.py` does `SERVICE.replace("-", "_")` rather than emitting `quotes-api_requests_total`, which would be rejected at registration. Doing it in code instead of in the scaffolder means a rename can never produce an invalid metric name, and `tests/test_api.py` asserts exactly that.

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
      # Kubernetes injects a Docker-link env var per Service in this namespace:
      # ORDER_API_PORT, ORDER_WORKER_PORT, PRICING_PORT, FRONTEND_PORT — each
      # set to "tcp://<clusterIP>:<port>". Any app reading a variable of that
      # name as its own config gets a URL where it expected an integer:
      #   ValueError: invalid literal for int() with base 10: 'tcp://10.96...'
      # Env vars outrank every other config source, so the app cannot win.
      # Service links are a Docker-links relic nothing here uses.
      enableServiceLinks: false
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
          # A scaffolded service is packaged as a PEX, which unpacks its
          # dependency closure on first run and therefore needs somewhere
          # writable. Under readOnlyRootFilesystem it has nowhere and dies in the
          # PEX bootstrap before any application log line appears:
          #   FileNotFoundError: No usable temporary directory found
          # Same mount order-api and pricing carry, for the same reason.
          volumeMounts:
            - { name: tmp, mountPath: /tmp }
      volumes:
        - { name: tmp, emptyDir: {} }
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
  annotations:
    # Same pair as order-api and frontend, and for the same reason: the edge is
    # outside the mesh, the backend is inside it under STRICT mTLS. Without
    # these, every scaffolded service comes up healthy and answers the browser
    # with "upstream connect error ... connection termination" — which is the
    # worst possible first experience of a paved path (§14.6), because the
    # service is fine and the template is what's broken.
    nginx.ingress.kubernetes.io/service-upstream: "true"
    nginx.ingress.kubernetes.io/upstream-vhost: "{{ $svc.name }}.{{ $.Release.Namespace }}.svc.cluster.local"
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

The portal is built by our own CI, on the same path as everything else — it's just a bigger image. It needs a Dockerfile CI can actually run, and a build step in the generator.

Write `portal/Dockerfile`, Backstage's [multi-stage build](https://backstage.io/docs/deployment/docker#multi-stage-build), and use it for every build of the portal — local and CI alike. `create-app` also generates `packages/backend/Dockerfile`; ignore it. That one is a *host build* that only copies a `dist/` you must have produced beforehand with a local Node toolchain, and our CI build step is a Buildah pod with no Node in it. The multi-stage file compiles the project inside the image, so `buildah bud` against the `portal` directory is self-contained.

**`portal/Dockerfile`**

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

> **Leave `packages/*/src` commented out.** `create-app` writes that exclusion for a host build, where `dist/` is already compiled; our multi-stage build compiles *from* those sources, and excluding them fails `yarn tsc` with `error TS18003: No inputs were found in config file '/app/tsconfig.json'` — an error that names `tsconfig.json` and never mentions Docker. `plugins` stays excluded, because the `COPY plugins plugins` line is commented out above.

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

> **Twenty to forty minutes, in a `vfs`-backed privileged pod, on your laptop.** That is the honest cost of building Backstage in-cluster, and `vfs` (which we chose in §12.5 because overlay-in-overlay needs privileges we'd rather not grant) is most of it. `branches: "main"` keeps it off every branch build; while you are iterating on the portal, build the same file on your laptop instead and let CI own it once it's stable:

```bash
docker build -f portal/Dockerfile -t nexus:8082/shop/portal:dev portal
docker push nexus:8082/shop/portal:dev
```

Three stages: a skeleton layer of nothing but `package.json` files so dependency installs cache, a build stage that runs `yarn tsc` and `yarn build`, and a production stage carrying only the bundle and production dependencies. It resolves npm through Nexus because `.yarnrc.yml` is copied in before `yarn install`, so the [§14.2](#142-first-an-npm-proxy-in-nexus) proxy applies to the container build too.

Backstage needs a database and a GitHub token. Without the token the catalog is empty and the scaffolder cannot open a pull request, so do this before the install rather than after.

Create a **fine-grained** personal access token at <https://github.com/settings/personal-access-tokens/new>:

- **Repository access** → *Only select repositories* → your fork of this repo.
- **Permissions** → *Repository permissions* → **Contents: Read-only** (Backstage reads `catalog-info.yaml` and the two template files) and **Pull requests: Read and write** (the scaffolder opens the PRs).

Nothing else. Generate it and copy the `github_pat_…` value — GitHub shows it once.

The token comes into the cluster from OpenBao through ESO, exactly like every other secret ([§7.6](phase-1-the-application.md#76-let-kubernetes-pull-from-nexus)). Store it at `shop/backstage` under the key `github_token`, which is what the `ExternalSecret` below reads:

```bash
kubectl create namespace backstage

kubectl -n openbao exec -it openbao-0 -- env BAO_TOKEN=root BAO_ADDR=http://127.0.0.1:8200 \
  bao kv put shop/backstage github_token='github_pat_...'
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
  # The chart sets `command: ["node","packages/backend"]` with empty args, which
  # DISCARDS the image's CMD — and the image's CMD is where the --config flags
  # live. Without these, Backstage loads only app-config.yaml, whose database
  # block is `client: better-sqlite3, connection: ':memory:'` for local dev. It
  # then dies trying to load a native sqlite binding that was never compiled,
  # and every plugin fails with "Failed to instantiate service 'core.auth'" —
  # an error that names neither the config nor the database.
  args:
    - "--config"
    - "app-config.yaml"
    - "--config"
    - "app-config.production.yaml"

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

> **Do not add `POSTGRES_*` to `extraEnvVars`.** With `postgresql.enabled: true` the chart already
> emits those four variables, and a second copy makes the install fail outright — server-side apply
> treats `env` as a list keyed by `name` and rejects duplicate keys. `extraEnvVars` is for the other
> case: point Backstage at a database you run yourself (`postgresql.enabled: false`) and you set
> `POSTGRES_*` there, because then the chart contributes nothing.

Push first. Backstage reads the catalog and both templates from GitHub over the URLs in
`app-config.production.yaml`, so those files have to be on `main` in your fork before the portal starts
looking for them:

```bash
git add portal catalog-info.yaml deploy/backstage deploy/platform/backstage-secrets.yaml \
        deploy/charts/order-platform infra/backstage-values.yaml .buildkite/pipeline.sh
git commit -m "feat(portal): backstage with service and infrastructure paved paths"
git push
```

Then install:

```bash
helm repo add backstage https://backstage.github.io/charts
helm repo update

kubectl apply -f deploy/platform/backstage-secrets.yaml

helm upgrade --install backstage backstage/backstage \
  --namespace backstage --version 2.10.0 \
  --values infra/backstage-values.yaml --wait
```

ESO refreshes on its own schedule, so restart the portal once to be certain it is running with the token you just stored:

```bash
kubectl -n backstage rollout restart deployment/backstage
kubectl -n backstage rollout status  deployment/backstage
```

Open **<https://backstage.localtest.me>** — `https`, not `http`. The frontend calls `crypto.randomUUID`, which browsers expose only in a secure context, so over plain http the UI loads a blank page and nothing else. The certificate is the ingress controller's self-signed default; accept the warning. Sign in as Guest and you should see the catalogue from §14.5 and both templates under **Create**.

> **The portal is the one thing here still deployed by `helm install` from your laptop** — imperatively, outside GitOps, with a tag you set by hand. That is a deliberate stopping point, not an oversight: making it an Argo CD `Application` and teaching CI to bump its tag is exactly the work of [§11.4](phase-3-delivery.md#114-the-app-of-apps) and [§12.5](phase-3-delivery.md#125-the-pipeline) applied one more time, and doing it yourself is a better test of whether those two sections landed than reading a third worked example. Note the irony while you're at it — **the tool whose entire job is paving paths for other people is, right now, the least paved thing in the cluster.** That is how platforms usually look.

> **Guest sign-in means there is no such thing as "who did that".** Every scaffolder run, every PR the portal opens, is attributed to the one GitHub token — so the audit trail says "the portal did it" and stops. That is tolerable on a laptop and indefensible anywhere else, because the portal's token is more privileged than any individual's. The production shape is GitHub OAuth for user identity plus the scaffolder acting as a GitHub App, so the PR is opened *on behalf of* the person who filled in the form. Wire that up before a second person uses your portal, not after.

> **The bundled PostgreSQL is a `bitnamilegacy` image, and that's a smell worth tracking.** The chart's default points at Bitnami's legacy registry, which is where images go once they stop being the maintained line. It works, and for a laptop it is fine. For anything durable, run Postgres you actually control — an operator, or a managed database — and set `postgresql.enabled: false` with `POSTGRES_*` pointing at it. **Never let your portal's database be the least-maintained component in your platform**, because when it dies you lose the catalog, and the catalog is what you'd have used to find out what depends on it.

---

## Where you are

Someone who has read none of this can add a service to your platform through a form, get a pull
request they can review, and have it built, deployed, meshed and monitored on merge — because every
one of those decisions was made once, here, by you.

**Next: [Phase 7 — One build system, many languages](phase-7-polyglot-monorepo.md).** Adding a service is now cheap, which is exactly what makes one build tool per language stop scaling.

[← All phases](README.md) · [← Phase 4 — Identity between services](phase-4-service-mesh.md) · [Phase 7 — One build system, many languages →](phase-7-polyglot-monorepo.md)

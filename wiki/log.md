# Log

Append-only. Newest last. One line per operation: date — what happened — pages touched.

---

- **2026-08-15** — Wiki created from `modern-devops-tutorial.md`. 24 tool pages, 11 concept pages,
  index, open questions. Every documentation URL verified with `curl` (all 200). Skills added:
  `wiki-ask`, `wiki-ingest`, `wiki-lint`. Schema written to `CLAUDE.md`.
- **2026-08-15** — `uv run pytest -q` failed building `pydantic-core` 2.33.2. Root cause: unpinned
  interpreter (`requires-python = ">=3.13"`, no `.python-version`) → uv chose Homebrew's 3.14.7 →
  no cp314 wheel → source build → pyo3 0.24.1 caps at 3.13. Fixed by `uv python pin 3.13` +
  `requires-python = ">=3.13,<3.14"`; venv rebuilt on 3.13.15, **8 tests pass, ruff clean**. Same
  latent defect fixed in the tutorial (§3.1) with a new callout. Pages: [[uv]] (new pinning section
  + verified wheel facts), [[fastapi]] (cross-link).

- **2026-08-16** — Built the platform on a live kind cluster through §13 and ran CI for real. Seven
  tutorial defects found by execution, all fixed in `modern-devops-tutorial.md` and recorded on the
  tool pages as `> [!warning]` blocks with exact symptoms:
  1. Floci crash-looped — `SRCFG00029: Expected an integer value, got "tcp://…:4566"`. Kubelet service
     links inject `FLOCI_PORT`; SmallRye reads it as `floci.port`. Fixed with `enableServiceLinks: false`.
  2. & 3. `rollout restart daemonset/ingress-nginx-controller` → `NotFound` in §13.2 and §17; the kind
     manifest ships a **Deployment**. A missed restart means nginx never gets its Istio sidecar.
  4. Argo CD UI documented as `http://` → endless login redirect, because the `argocd.token` cookie is
     `Secure` and browsers discard it over plain HTTP. Now `https://`.
  5. Buildkite queue must be **Self-hosted**; the New Queue form defaults to Hosted and the failure
     presents as a Git auth error about `buildkite-plugins/kubernetes-buildkite-plugin`.
  6. §5.3 said *disable* anonymous Nexus access while §12.5 fetches from the proxies with no
     credentials — `401 Unauthorized` for Go, a silent hang for uv. Global anonymous access does not
     expose `docker pull` (separate per-repository switch), so §7's lesson is intact.
  7. `uv sync --locked` failed on a freshly committed lock: `uv.lock` records the registry, and an
     index set only in CI can never match it. Index moved into `pyproject.toml`; `UV_INDEX_URL` (also
     deprecated) dropped from the pipeline. Plus `go test -race` needs cgo — test step moved from
     `golang:1.26-alpine` to `golang:1.26`.
  Also diagnosed but not a tutorial defect: an Argo CD cascade delete wedged ~80 minutes on a
  `KafkaTopic` whose `strimzi.io/topic-operator` finalizer could never be satisfied, because the
  `Kafka` CR hosting the topic operator was deleted first. Pages: [[sonatype-nexus]], [[buildkite]],
  [[uv]], [[go]], [[argo-cd]], [[strimzi]], [[floci]], [[ingress-nginx]], [[index]],
  [[open-questions]].
- **2026-08-16** — Eighth tutorial defect, found when `order-platform` would not deploy: the chart
  shipped `podMonitor.enabled: true`, but `monitoring.coreos.com` CRDs only arrive with
  kube-prometheus-stack in §13.2 — two sections after Argo CD begins syncing the app in §11.4.
  Argo CD fails an Application sync **as a unit**, so every workload in `shop` stayed `Missing` while
  only the `PodMonitor` row carried an error message. §11.4–§12.6 were unreachable as written.
  Defaulted the flag `false` in the chart's own `values.yaml` (not the `env/local` overlay, which
  Buildkite rewrites wholesale) and moved the flip into §13.3, where it doubles as the tutorial's
  first change delivered to the cluster purely through git. Verified: `helm template` renders 0
  PodMonitors by default and 1 with `--set podMonitor.enabled=true`, with the other seven resources
  unchanged. Pages: [[argo-cd]], [[prometheus]].
- **2026-08-16** — Contradiction found and resolved while fixing the PodMonitor gate: [[prometheus]]
  said Istio's merged metrics endpoint was *"port 15020 (`http-envoy-prom`)"*, attaching the port name
  to the wrong port. Settled against a live injected pod (`ingress-nginx-controller`): the name
  `http-envoy-prom` belongs to **15090** (Envoy only), while the **merged** endpoint is **15020**,
  unnamed and advertised only through `prometheus.io/port`. The tutorial (§10.1) was already correct;
  the wiki was wrong and now says so explicitly rather than being quietly overwritten.
  This raises a live question about the chart itself — its `PodMonitor` selects `port:
  http-envoy-prom`, i.e. 15090, which may mean application metrics are never scraped at all. Recorded
  in [[open-questions]] rather than acted on: settling it needs a meshed `order-api` pod and a real
  scrape, neither of which exists yet. Pages: [[prometheus]], [[open-questions]].
- **2026-08-16** — Traffic generated against `shop.localtest.me` produced empty graphs. Three causes,
  none of them the dashboards. (a) All four pods were `ImagePullBackOff` on
  `nexus:8082/shop/order-api:dev` — the registry holds real SHA tags but `env/local/values.yaml` still
  says `dev`, because the deploy step is `branches: "main"` and no build has completed on main yet.
  Not a defect; the tag arrives with the first green build. (b) The `shop` namespace had lost
  `istio-injection=enabled`: §9.3 applied it with `kubectl label`, but [[argo-cd]] recreates the
  Namespace from `deploy/platform/` on any teardown and an imperative label does not come back.
  Moved into the manifests for `shop` and `floci`; only `ingress-nginx` stays imperative, since
  nothing in `deploy/` declares it. (c) Settled the open PodMonitor question — **it was wrong**. The
  chart scraped `port: http-envoy-prom` = 15090 = Envoy-only, so `istio_requests_total` (and therefore
  [[kiali]]) worked while the application's own `orders_received_total` never appeared: a silent
  half-failure that §13.3's check would have caught with no explanation. Istio's docs are explicit
  that 15020 carries merged metrics and 15090 Envoy-only; a live sidecar agrees. Fixed to
  `portNumber: 15020` — 15020 is unnamed so `port:` cannot address it, and `targetPort` is deprecated
  by the CRD in favour of `portNumber`. Verified with `kubectl apply --dry-run=server`. Pages:
  [[prometheus]], [[istio]], [[gitops]], [[open-questions]].
- **2026-08-16** — Build #8 hung for 20+ minutes on `build order-worker`, and two earlier builds with
  it, exhausting the Buildkite concurrency limit. Cause: [[buildah]] refuses to guess a registry for an
  unqualified image name. `quay.io/buildah/stable` ships three `unqualified-search-registries` and
  `short-name-mode = "enforcing"`, so `FROM golang:1.26-alpine` produced an interactive
  *"Please select an image"* prompt; the build pod has a TTY, so it waited forever. Without a TTY the
  same command exits 125 in a second, which is why it never reproduced locally. `python:3.13-slim` had
  been resolving silently only because Buildah's bundled `000-shortnames.conf` aliases `python` and
  not `golang` — luck, not design. All `FROM` lines are now fully qualified.
  Found alongside it: a manually-triggered build sets `BUILDKITE_COMMIT` to the literal string `HEAD`,
  so the pipeline had pushed `shop/order-api:HEAD` — a mutable tag, precisely what
  [[immutable-image-tags]] forbids. `pipeline.sh` now resolves it with `git rev-parse` and refuses to
  build on any non-hex value. Verified all three cases (`HEAD`, a real SHA, garbage → exit 1).
  Pages: [[buildah]], [[immutable-image-tags]].
- **2026-08-16** — `platform` reported `OutOfSync` on three ExternalSecrets while `argocd app diff`
  and `kubectl diff` both showed **no difference**, on the exact revision Argo had synced. Cause: the
  ExternalSecrets CRD defaults seven fields the API server injects and git does not carry
  (`deletionPolicy`, `engineVersion`, `mergePolicy`, `conversionStrategy`, `decodingStrategy`,
  `metadataPolicy`, `nullBytePolicy`). [[argo-cd]] diffs **client-side** by default and reads every
  one of them as drift; `kubectl diff` misses it because it is already a dry-run server-side apply —
  which is the fix. Added `argocd.argoproj.io/compare-options: ServerSideDiff=true` to the `platform`
  Application. It is an annotation, not a syncOption, and `ServerSideApply=true` alone is not enough:
  applying server-side while diffing client-side is what creates the permanent false positive.
  Verified live — `Synced` after a hard refresh. General rule recorded: an `OutOfSync` resource with
  an empty diff is a diff-strategy problem, not drift. Pages: [[argo-cd]].
- **2026-08-16** — `yarn --cwd packages/backend add @backstage/plugin-scaffolder-backend-module-github`
  failed with `Unrecognized or legacy configuration settings found: npmMinimalAgeGate`. Cause: §14.3
  ran `yarn set version 4.4.1` immediately after `create-app@latest`, downgrading Yarn below the
  scaffold's own `.yarnrc.yml`. `npmMinimalAgeGate` (and `npmPreapprovedPackages`) arrived in **Yarn
  4.12**, so a 4.4.1 binary cannot parse the config `create-app` had just written — and the parse
  error blocks every Yarn command, including `yarn set version` itself. Fixed by removing the
  backwards pin from the tutorial: `packageManager` in `package.json` is already the reproducibility
  guarantee and Corepack honours it. Local checkout moved 4.4.1 → 4.18.0 via `yarn set version
  stable`; `yarn config get npmMinimalAgeGate` now returns 4320 (3d).
  Not a defect, but recorded because it looked like one: the next failure was
  `404 (Repository not found)` from `nexus:8081/repository/npm-proxy/` — §14.2 creates that proxy and
  had simply not been run. Nexus returns 404 for a missing *repository* and 401 for a missing
  credential; reading which one you got saves a wrong turn. Pages: [[backstage]].
- **2026-08-16** — Wrote the `new-service` skeleton the tutorial had left as "mechanical, copy from
  order-api": `app/{__init__,main,settings}.py`, `tests/{__init__,test_api}.py`, `pyproject.toml`,
  `uv.lock`, `Dockerfile`, `.python-version`. Three parts were not mechanical. (a) `uv.lock` is
  **templated** — the project name appears in it exactly once, so the scaffolder rewrites it with
  `pyproject.toml` and `uv sync --locked` keeps working; dropping the lock instead would have made
  scaffolded services less reproducible than the hand-written service they copy, which is how a paved
  path stops being used. (b) The skeleton's `pyproject.toml` declares the [[sonatype-nexus]] index, or
  every generated service silently resolves from pypi.org past the choke point. (c) The Prometheus
  metric prefix is computed as `SERVICE.replace("-", "_")` at runtime, because hyphenated service
  names are invalid metric names — with a test asserting it. Verified by rendering the skeleton under
  **two different names** and running the real CI contract in `python:3.13-slim` against Nexus
  (`uv sync --locked`, ruff, 6 tests pass) plus a `buildah bud` on the kind network, which is what CI
  actually runs. Pages: [[backstage]], [[paved-paths]].
- **2026-08-16** — Backstage chart 2.10.0 refused to install: `duplicate entries for key
  [name="POSTGRES_HOST"]` (and PORT, USER, PASSWORD) on the backend Deployment. §14.8's values set
  those four in `extraEnvVars` while `postgresql.enabled: true` makes the chart emit them itself, so
  every key rendered twice. Server-side apply treats `env` as a list keyed by `name` and rejects
  duplicates outright — client-side apply used to keep the last silently, which is why the pattern
  survives in older values files. Verified the chart's generated values are byte-identical to the
  hand-added ones, so removing the block changes nothing about the pod; `helm ... --dry-run=server`
  then reports `pending-install` with no duplicates. Also recorded the follow-on trap: the failed
  revision leaves a Helm-owned `backstage-postgresql` Secret and the retry fails *differently*
  (`PASSWORDS ERROR ... does not contain the key "user-password"`) until `helm uninstall` clears it.
  Pages: [[backstage]].
- **2026-08-16** — Backstage pod: `no basic auth credentials` pulling `nexus:8082/shop/portal:dev`.
  Two omissions in §14.8, both from secrets not crossing namespaces: `backstage-secrets.yaml` created
  only `GITHUB_TOKEN`, so the `backstage` namespace had no `dockerconfigjson` at all (§7's
  `nexus-pull` is in `shop`), and `infra/backstage-values.yaml` never set
  `backstage.image.pullSecrets`, which the chart exposes and defaults to `[]`. Added an
  [[external-secrets-operator]] ExternalSecret for `nexus-pull` in `backstage` plus the values entry.
  Verified: the ExternalSecret reached `SecretSynced` in 5s, its credential returns HTTP 200 against
  `nexus:8082/v2/_catalog`, the pod now carries `imagePullSecrets: [nexus-pull]`, and the kubelet
  error changed from `no basic auth credentials` to plain `NotFound` — which is the *authenticated*
  answer and the useful diagnostic: `no basic auth credentials` means a missing Secret, `not found`
  means a missing image. Remaining blocker is genuinely the image: `shop/portal` has never been
  built, since the `build-portal` step is `branches: "main"`. Pages: [[backstage]].
- **2026-08-16** — Build #22 on `main`: six of seven steps green, `build portal` failed in 24s with
  `copier: stat: "/packages/backend/dist/skeleton.tar.gz": no such file or directory` (exit 125).
  §14.8 pointed CI at `portal/packages/backend/Dockerfile`, which `create-app` generates as a **host
  build** — its own header requires `yarn install --immutable && yarn tsc && yarn build:backend` to
  have run first. It *copies* the skeleton tarball, it never creates one, and the CI step is a
  [[buildah]] pod with no Node toolchain. The tutorial's host-build suggestion had the same omission.
  Added `portal/Dockerfile` — Backstage's documented three-stage
  [multi-stage build](https://backstage.io/docs/deployment/docker#multi-stage-build) — and pointed
  the pipeline at it, keeping the host-build file for local iteration. Two adjustments were needed
  beyond the published version: `COPY plugins plugins` had to go, since `create-app` leaves
  `plugins/` holding only a README **and** `.dockerignore` excludes `plugins` outright, and the three
  `FROM node:24-trixie-slim` lines were fully qualified — Buildah resolved `node` only via its
  shortname alias list, the same luck that `python` had and `golang` did not (see [[buildah]]).
  Pages: [[backstage]], [[buildah]].
- **2026-08-16** — Full audit of the repo against `modern-devops-tutorial.md`, mechanically rather
  than by reading. Extracted all 51 ``**`path`** + fenced block`` listings and diffed each against the
  real file. Result: **0 missing files**, 47 exact matches, and 4 declared partials that were proven
  correct rather than waved through — the two `.buildkite/pipeline.sh` halves (§12.5 + §14.8) were
  shown to reconstruct the file byte-for-byte, and every line of the `portal/.yarnrc.yml` and
  `packages/backend/src/index.ts` fragments was confirmed present in the real file.
  Seven drifts found and fixed, all of them cases where a fix had landed in a file but only half in
  the tutorial: the `pyproject.toml` uv-index comment, the `values.yaml` `scaffolded:` block, the
  PodMonitor 15020 rationale, the `nexus-pull` ExternalSecret in `backstage-secrets.yaml`, a
  `golang:1.26` rationale block that existed only in the tutorial and not in `pipeline.sh`, and two
  files CI depends on that the tutorial never listed at all — `portal/Dockerfile` and
  `portal/.dockerignore`. §14.8 also still claimed `packages/backend/Dockerfile` "already contains"
  the multi-stage build, which is the false statement that produced the exit-125 failure; corrected.
  Also swept 50 internal `§` anchors (one broken: `#12-buildkite-ci`) and re-verified the version
  matrix by reading versions back off the **live cluster** — two were wrong: Yarn (4.4.1 → 4.18.0,
  the value removed as a defect) and kube-prometheus-stack (82.14.1 → 88.3.0, which is what is
  actually installed and what §13 was validated on). Pages: [[log]].
- **2026-08-16** — Produced a **phased edition** of the tutorial in `docs/`: seven phases that each
  end in something working and checkable, plus a README explaining why that order. Section numbers
  are preserved verbatim, so every `§N.M` citation in this wiki resolves against either edition.
  Assembly was mechanical (extract by heading, rewrite cross-file anchors, verify every link) rather
  than hand-copied, so the two editions cannot silently drift in the parts they share: all 16
  numbered sections placed exactly once, §0 became the README, 0 broken links across 9 files.
  Three places genuinely differ, because reordering changes what is true when — recorded here so the
  difference is not mistaken for drift:
  1. Phase 1 installs the app with `helm install` (new §10.4 build-by-hand and §10.5 install) and
     Phase 3 hands the release to [[argo-cd]] with an explicit `helm uninstall`. The single-doc
     edition never deploys the app until Argo does.
  2. Observability comes **before** the mesh, so Phase 2 scrapes with a `ServiceMonitor` on the app's
     own port. This required a new chart template, `servicemonitor.yaml`, plus a
     `serviceMonitor.enabled` value — exactly one of the two monitors should ever be on.
  3. §9.6 becomes the moment STRICT mTLS breaks that scrape and you swap to the `PodMonitor` on
     15020. In the single-doc order the mesh precedes monitoring, so the same lesson can only be told
     retrospectively.
  The reordering also fixes a latent oddity in the original: Istio arrived at §9, enabling STRICT
  mTLS on a `shop` namespace that had no workloads in it yet. Pages: [[argo-cd]], [[prometheus]],
  [[istio]], [[order-platform]].
- **2026-08-16** — **Polyglot monorepo documented.** Four new pages — [[pants]], [[pex]], [[grpc]],
  [[vite]] — plus a new phase document `docs/phase-7-polyglot-monorepo.md` (§17 Pants, §18 one proto
  two languages, §19 pricing / PEX / frontend / CI), and the canary added to `docs/phase-4` as §9.8
  (DestinationRule subsets, 90/10 VirtualService weights, the retry arithmetic, outlier detection)
  and §9.9 (the fault-injection drill). Source: the four implementation commits on
  `feat/pants-polyglot-grpc` (`ccf317d`, `9bd0086`, `5a94af4`, `3e31724`, `ae9a448`), the manifests
  and BUILD files themselves, and Context7 for the [[pex]] and [[pants]] vendor claims.
  Seven failures recorded, each on the page where a reader will hit it:
  `complete_platforms` (a PEX that builds clean and dies on import in the container),
  `PEX_ROOT` under `readOnlyRootFilesystem` (fails in the bootstrap, so no application log line
  appears), `Duplicate module named "app"` (a property of the source-root layout, not of those
  services), Pants' JS/TS backend not inferring a build script's config or asset inputs (a missing
  `style.css` produced a green build and an unstyled page), the ruff backend path in 2.33 failing as
  a `ModuleNotFoundError`, Homebrew's interpreter being invisible to `[python-bootstrap]`, and
  Istio detecting gRPC from the **Service port name** (wrong name = silent TCP passthrough, so the
  entire canary applies successfully and does nothing).
- **2026-08-16** — **A documented claim was found to be false and corrected**, per rule 7 recorded
  rather than overwritten. §3.2 and [[go]] both stated that `-ldflags "-X main.version=…"` stamps the
  build SHA into the `order-worker` binary at link time. It does not: `main.go` declares no
  `var version string`, and Go's linker silently does nothing when the `-X` target symbol is absent.
  The version a running worker reports has always come from `SERVICE_VERSION`, set by the chart from
  the image tag. The `ARG VERSION`, the `--build-arg VERSION=$SHA` and the pipeline's per-service
  `BUILD_ARGS` special case were plumbing for a mechanism that never ran once. Source won: the source
  code, over both documents. Callouts added to `modern-devops-tutorial.md` §3.2,
  `docs/phase-1-the-application.md` §3.2, and [[go]]; the `-ldflags` listing itself is left intact
  with the correction beside it. `-s -w` and `-trimpath` were and are real.
- **2026-08-16** — **Two stale claims corrected in the phased edition, and one recorded but not
  fixed.** `docs/phase-5` listed the Backstage skeleton as emitting `app/`; commit `ae9a448` had
  already templated it to `${{ values.name | replace("-", "_") }}` to stop the paved path
  manufacturing the duplicate-module failure. Corrected, with the reason. Recorded and **not** fixed:
  `deploy/charts/order-platform/templates/pricing.yaml` cites *"§9.6 DestinationRule"* when the
  DestinationRule is §9.8 — the fix belongs in the manifest, and a documentation pass should not edit
  deployed YAML. Flagged in `docs/phase-4` §9.8.

||||||| 12e1572

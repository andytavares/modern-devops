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

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

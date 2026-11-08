---
type: tool
tags: [chart, application, packaging]
role: the app this platform exists to deliver, and the chart that deploys it
version: chart 0.1.0; image tags are the 12-char commit SHA
docs: https://helm.sh/docs/topics/charts/
date_added: 2026-08-17
date_updated: 2026-08-17
status: in-use
---

# order-platform

> [!info] One-liner
> One [[helm]] chart, five workloads plus whatever the paved path added. Every deployment decision in this platform is visible in one directory: `deploy/charts/order-platform/`.

## What it deploys

| Workload | Language | Port(s) | Replicas |
|---|---|---|---|
| `order-api` | [[fastapi]] | 8000 (`http`) | 2 |
| `order-worker` | [[go]] | 9090 (`http-metrics`) | 2 |
| `pricing-v1` | [[grpc]] / Python | 50051 (`grpc`), 9090 (`http-metrics`) | 2 |
| `pricing-v2` | same image, `PRICING_VERSION=v2` | same | 1 |
| `frontend` | [[vite]] + nginx | 8080 | 2 |
| `<scaffolded>` | one Deployment per `services/*.yaml` | 8000 | 1 |

> [!warning] The chart in the repo is ahead of §10.1's listing, and that is correct
> §10.1 shows `values.yaml` before `pricing`, `frontend`, `podDisruptionBudget` and the `aws.*`
> credential keys exist, because Phase 1 comes before Phase 7. That is [[progressive-build]] working as
> designed, and `checks/verify_doc_listings.py` enforces the rule that only the **last** listing of a
> file must match the repo.

## The values contract

`values.yaml` holds defaults. `deploy/env/local/values.yaml` is **the deployment contract** —
[[buildkite]] rewrites it wholesale on every build and commits, [[argo-cd]] syncs. Nothing else writes
there.

> **Every service the chart can deploy needs a tag in the overlay.** One that is missing falls back to
> the chart default `"dev"` — an image CI never builds — and **only that service fails.** The overlay
> currently carries `orderApi`, `orderWorker`, `pricing.v1`, `pricing.v2`, `frontend` and `scaffolded`.

Anything that must **not** be rewritten by CI — the `podMonitor`/`serviceMonitor` toggles above all —
belongs in the chart's `values.yaml`, never the overlay.

## Decisions encoded in the templates

**Rollout strategy differs per workload, on purpose.** order-api takes `maxSurge: 1,
maxUnavailable: 0` so capacity never dips — costing one pod of headroom and forcing
backwards-compatible changes. order-worker takes `maxSurge: 0, maxUnavailable: 1`, because a consumer
group rebalances on every membership change and surging would cause **two** rebalances per pod instead
of one.

**`securityContext` on every container**: `runAsNonRoot`, `seccompProfile: RuntimeDefault`,
`allowPrivilegeEscalation: false`, `readOnlyRootFilesystem: true`, `capabilities: drop: [ALL]`.
Read-only roots are why every [[pex]] service needs a `/tmp` emptyDir.

**`enableServiceLinks: false` on every pod template** — see [[kubernetes]].

**`checksum/config` annotations** so a value change actually rolls the pods. `pricing.yaml` hashes
*its own ConfigMap* rather than `.Values`, because CI rewrites tags in the overlay on every build and
hashing `.Values` would restart every pod in the namespace every time.

**PodDisruptionBudgets, but only above one replica.** The `op.pdb` helper renders nothing below two,
because `minAvailable: 1` against a single replica permits **zero** voluntary evictions and blocks a
node drain forever. `pricing-v2` runs one replica and is therefore drainable — the correct answer for a
canary, and the reason the helper takes the replica count rather than assuming it.

**The label set is Helm's recommended one; the selector deliberately is not.** See [[kubernetes]].

**`op.commonEnv`** is the shared env block — Kafka brokers, AWS endpoint and region, and the Floci
credential sentinels. *Keeping this in one place is the whole reason we wrote a chart instead of two
YAML files.*

## `checks/verify_chart.py` — three assertions nothing else makes

Run in CI as `helm template … | python3 checks/verify_chart.py -`. Rendering the chart is the
expensive part, so all three ride along on the same manifests:

1. **`frontend/nginx.conf`'s `proxy_pass` port matches the port order-api's Service publishes.** Point
   nginx at 8000 (the *container* port, which nothing serves on the ClusterIP) and every order in the
   dashboard reads `HTTP 502` while a direct `curl` returns `202` — sending you to the wrong service
   entirely. The chart is valid, the nginx config is valid, both images build, every pod is Ready.
2. **No probe names a port its container does not declare.**
3. **No Service `targetPort` names a port no selected pod declares.**

> **Check the rendered chart, never the template.** A template read as text is
> `targetPort: {{ .Values.orderApi.port }}` — a text check either hard-codes the answer it is supposed
> to discover or reimplements Helm's evaluation. That is Helm's own documented debugging flow.

The general pattern: **when a fact is duplicated across a language boundary, the monorepo lets you
assert it in a check that runs on every build.** Same argument as [[grpc]]'s cross-language compile
check, applied to config.

## The other checks in `checks/`

- `build_single_edition.py` assembles `modern-devops-tutorial.md` from `docs/`, in **build order rather
  than section-number order**. `test_docs_are_current.py` fails if the committed file differs.
- `verify_doc_listings.py` asserts every bolded path a listing names exists, and that the **last**
  listing of each file matches the repo. See [[progressive-build]].

## Related

[[helm]] · [[argo-cd]] · [[fastapi]] · [[go]] · [[grpc]] · [[vite]] · [[pex]] · [[kubernetes]] · [[istio]] · [[prometheus]] · [[paved-paths]] · [[progressive-build]]

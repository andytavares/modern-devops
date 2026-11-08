---
type: tool
tags: [ci, delivery]
role: hybrid CI — SaaS control plane, agents on our infrastructure
version: agent-stack-k8s 0.46.3
docs: https://buildkite.com/docs/agent/self-hosted/agent-stack-k8s/installation
date_added: 2026-08-17
date_updated: 2026-08-17
status: in-use
---

# Buildkite

> [!info] One-liner
> The control plane is SaaS; the agents run in your cluster and poll it outbound. Its total privilege in this platform is **push a commit** — it holds no kubeconfig.

## The hybrid model, and its one honest caveat (§12.1)

The control plane (buildkite.com) holds pipeline definitions, schedules jobs and renders the UI. The
agents run on your compute and poll over outbound HTTPS. Consequence: **no inbound firewall holes, and
build secrets never leave your infrastructure.** The control plane knows a job ran and whether it
passed; it never sees your source, your registry credentials, or your artifacts.

**The caveat, stated plainly: there is no offline Buildkite.** Every other component here runs entirely
on your laptop; this one does not. For a fully air-gapped lab, substitute Woodpecker CI or Concourse —
the pipeline *shape* (test → build → push → commit a tag) is portable, and so is generating it from a
script. Only the YAML dialect is not.

## agent-stack-k8s

A controller that watches Buildkite for jobs tagged with your queue and creates a Kubernetes **Job per
build step**. Each step gets a fresh pod, so builds are isolated by construction.

`infra/buildkite-values.yaml` sets `config.tags: [queue=kubernetes]` and a
`default-checkout-params.gitCredentialsSecret`, so every job's checkout container can clone without
repeating it per step. The agent-token Secret key **must** be exactly `BUILDKITE_AGENT_TOKEN`.

> [!warning] The queue must be created as **Self-hosted**, not Hosted
> The form defaults to Hosted, and the infrastructure type **cannot be changed after creation** —
> delete the queue and recreate it. A hosted queue runs jobs on Buildkite's machines, which do not
> understand the `kubernetes` plugin, so the build fails cloning
> `buildkite-plugins/kubernetes-buildkite-plugin` and the controller logs
> `job tags do not match expected tags in configuration` (§12.2, Appendix B).

> [!warning] `agents: { queue: kubernetes }` is not optional on any step
> An untagged step lands on the cluster's *default* queue, where no agent advertises, and sits at
> "waiting for agent" forever with no error.

## The pipeline is generated, not committed (§12.5)

The UI-side pipeline is **one step**: `.buildkite/upload.sh`. The real definition is emitted by
`.buildkite/pipeline.sh`, so pipeline changes are reviewed in PRs alongside the code they build.
**Never grow the UI-side pipeline beyond that step.** See [[dynamic-pipelines]] for why a generator,
and what it costs.

Current shape, as the repo actually ships it:

1. **Loop guard** — if `HEAD` is a `chore(deploy):` commit, emit a one-step no-op pipeline and exit.
2. **`lint · typecheck · test · package`** — one step, running the prebuilt
   `nexus:8082/ci/pants:0.13.2-2` image: `pants update-build-files --check lint check test ::`,
   `checks/verify_doc_listings.py`, `helm lint --strict`, `helm template | checks/verify_chart.py`,
   then `pants --tag=deployable package ::`. Artifacts to `dist/*`. See [[pants]].
3. **`wait`**
4. **One [[buildah]] step per discovered service**, build context `dist/`.
5. **Frontend and portal steps** — neither consumes a Pants artifact; the portal is `branches: "main"`
   only, because it takes 20–45 minutes.
6. **`wait`, then the deploy step** — rewrite `deploy/env/local/values.yaml` wholesale and push
   `chore(deploy): order-platform <sha> [skip ci]`.

**Services are discovered, not listed.** A directory under `services/` with **both** a `BUILD` and a
`Dockerfile` is a service, and that is the entire contract — which is what lets [[backstage]]'s paved
path add one without touching CI. `BUILD` rather than `Dockerfile` alone is the honest signal: a
directory Pants does not know about cannot be linted, tested or packaged.

## Five things in the pipeline that are load-bearing

**`BUILDKITE_COMMIT` can be the literal string `HEAD`** on a build triggered by hand in the UI, which
would tag images `:HEAD` — a mutable tag. The script resolves it to a real SHA and refuses to build
anything that is not one. See [[immutable-image-tags]].

**No pipe in `upload.sh`.** The obvious `pipeline.sh | buildkite-agent pipeline upload` hides failures:
a pipe's exit status is the *last* command's, so a generator that dies half-way still uploads what it
printed and the step goes green. Writing to a file under `set -e` fails the build instead. The
`--dry-run` and the artifact upload are not decoration either.

**Quoted heredocs.** `<<'YAML'` passes text through untouched; `<<YAML` substitutes. Get it backwards
and `$$` meets `sh`, where it is the process ID — you emit an image name like
`/shop/order-api:8412REGISTRY` and spend an afternoon on it. **Never emit a literal `$`; resolve it
while writing the YAML.**

**CI never touches the cluster.** No kubeconfig, no cluster token, no `helm` binary in the deploy step.
Compromise the pipeline and the attacker gets a reviewable, revertible commit.

**`chmod +x` both scripts, and check they made it into git** — `git ls-files -s .buildkite` must show
`100755`.

## Why diff-scoping is not here (§12.5)

Two independent reasons. **Scoping the builds breaks the deploy contract**: `deploy/env/local/values.yaml`
carries every tag and the deploy step rewrites all of them, so skipping a build stamps a SHA that was
never pushed → `ImagePullBackOff`. **Scoping the tests is worse, because it is silent**: services are
discovered from the filesystem, so every service gets an image whatever the tests did — you ship an
image whose code was never tested, and no step fails. Diff-scoping is a matched pair or it is a
hazard. Fix the contract first. [[pants]]' own caching makes the speedup smaller than it looks anyway.

## Related

[[dynamic-pipelines]] · [[buildah]] · [[argo-cd]] · [[pants]] · [[sonatype-nexus]] · [[immutable-image-tags]] · [[gitops]]

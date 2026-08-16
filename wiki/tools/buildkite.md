---
type: tool
tags: [ci, pipelines]
role: Continuous integration — hybrid SaaS control plane, self-hosted agents
version: agent-stack-k8s 0.46.3
docs: https://buildkite.com/docs/pipelines
date_added: 2026-08-15
date_updated: 2026-08-16
status: in-use
---

# Buildkite

> [!info] One-liner
> CI split in two: a hosted control plane that schedules, and agents on your own infrastructure that actually build.

## What it is

The **control plane** (buildkite.com) holds pipeline definitions, schedules jobs and renders the UI.
The **agents** run on your compute, inside your network, polling over an outbound HTTPS connection.

The consequence: no inbound firewall holes, and build secrets never leave your infrastructure. The
control plane knows a job ran and whether it passed; it never sees your source, registry credentials
or artifacts. That is why Buildkite shows up in regulated environments.

> [!warning] The honest caveat
> **There is no offline Buildkite.** Every other component in this platform runs on your laptop; this
> one does not. For an air-gapped lab, substitute Woodpecker CI or Concourse — the pipeline *shape*
> (test → build → push → commit a tag) is portable; the YAML dialect is not.

## What it does here

`agent-stack-k8s` (§12.3) is a controller that watches for jobs tagged `queue=kubernetes` and creates
a **Kubernetes Job per build step** — every step gets a fresh pod, so builds are isolated by
construction. The `kubernetes` plugin is how a step describes the pod it wants.

The pipeline is **dynamic**: `.buildkite/pipeline.sh` generates YAML on stdout and `.buildkite/upload.sh`
validates and uploads it (§12.5). See [[dynamic-pipelines]] for why that beats a static file.

Pipeline shape: test (parallel) → build+push images via [[buildah]] → write the image tag into git →
[[argo-cd]] takes it from there. **CI never touches the cluster.**

## Key concepts

- **Every job belongs to a queue.** A step with no `agents: { queue: ... }` tag lands on the cluster's
  *default* queue — where no agent is listening — and waits forever with no error (§12.2).
- **A queue is Hosted or Self-hosted, chosen at creation and never changeable.** The New Queue form
  defaults to **Hosted**, which runs jobs on Buildkite's machines. `agent-stack-k8s` can only service
  a **Self-hosted** queue. The queue's Settings page offers description, capacity and Delete — there
  is no conversion.
- **The controller matches tags exactly.** Buildkite's docs: *"The Buildkite Agent Stack for
  Kubernetes controller requires a matching `queue` tag for jobs to be processed... Jobs without an
  explicit `queue` tag, even for default cluster queues, will be skipped by the controller."*
- **`$` is interpolated at upload time**, in the agent's environment, before any container exists.
  `$$VAR` escapes it. Our generator sidesteps this entirely by substituting values as it writes.
- **Build steps are Jobs**, so the `buildkite` namespace must stay out of the mesh — a classic sidecar
  keeps the pod alive after the build container exits (§9.3).
- The UI-side pipeline stays one bootstrap step. The real definition lives in the repo, reviewed in PRs.

## Gotchas

> [!warning] A Hosted queue fails as a Git authentication error, 2026-08-15
> The `kubernetes` queue was created as **Hosted**. Everything looked correct — queue `Connected`,
> `agent-stack-k8s` pod `Running`, builds starting — but jobs ran on Buildkite's machines. Two
> symptoms, one cause:
>
> 1. The controller logged, on a loop:
>    `job tags do not match expected tags in configuration, skipping`, with
>    `controller-tags=map[queue:kubernetes]` versus
>    `buildkite-job-tags="map[namespace-experiments:docker.builder=local queue:kubernetes]"`.
>    The hosted agent adds a Namespace remote-builder tag the controller doesn't advertise.
> 2. The hosted agent then ran the job, hit the `kubernetes` plugin — which `agent-stack-k8s`
>    *interprets* rather than downloads — tried to clone it, and died:
>    `Can't issue repository access token: The repo you've requested a token for
>    (buildkite-plugins/kubernetes-buildkite-plugin) is in a different org to the repo for this job`
>    → `failed to checkout plugin kubernetes: exit status 128`.
>
> **A Git auth error naming a repository you've never heard of is what a Hosted queue looks like.**
> Fix: delete the queue, recreate as Self-hosted. Zero cluster-side changes were needed.

- Deprecated `agent-stack-k8s` note: versions ≤ 0.28.1 required `--set-json='config.tags=...'` to set
  the queue; later versions default to `queue=kubernetes`.

## Official docs

- Pipelines: https://buildkite.com/docs/pipelines
- agent-stack-k8s troubleshooting: https://buildkite.com/docs/agent/self-hosted/agent-stack-k8s/troubleshooting
- Dynamic pipelines: https://buildkite.com/docs/pipelines/configure/dynamic-pipelines
- Agent Stack for Kubernetes: https://buildkite.com/docs/agent/self-hosted/agent-stack-k8s
- `pipeline upload` CLI: https://buildkite.com/docs/agent/v3/cli-pipeline

> [!tip] Related
> [[dynamic-pipelines]], [[buildah]], [[argo-cd]], [[immutable-image-tags]], [[sonatype-nexus]]

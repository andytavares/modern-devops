---
type: tool
tags: [ci, pipelines]
role: Continuous integration — hybrid SaaS control plane, self-hosted agents
version: agent-stack-k8s 0.46.3
docs: https://buildkite.com/docs/pipelines
date_added: 2026-08-15
date_updated: 2026-08-15
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
- **`$` is interpolated at upload time**, in the agent's environment, before any container exists.
  `$$VAR` escapes it. Our generator sidesteps this entirely by substituting values as it writes.
- **Build steps are Jobs**, so the `buildkite` namespace must stay out of the mesh — a classic sidecar
  keeps the pod alive after the build container exits (§9.3).
- The UI-side pipeline stays one bootstrap step. The real definition lives in the repo, reviewed in PRs.

## Official docs

- Pipelines: https://buildkite.com/docs/pipelines
- Dynamic pipelines: https://buildkite.com/docs/pipelines/configure/dynamic-pipelines
- Agent Stack for Kubernetes: https://buildkite.com/docs/agent/self-hosted/agent-stack-k8s
- `pipeline upload` CLI: https://buildkite.com/docs/agent/v3/cli-pipeline

> [!tip] Related
> [[dynamic-pipelines]], [[buildah]], [[argo-cd]], [[immutable-image-tags]], [[sonatype-nexus]]

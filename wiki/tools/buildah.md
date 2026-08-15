---
type: tool
tags: [containers, build, ci]
role: Builds and pushes OCI images inside CI pods
version: quay.io/buildah/stable:v1.40.1
docs: https://buildah.io/
date_added: 2026-08-15
date_updated: 2026-08-15
status: in-use
---

# Buildah

> [!info] One-liner
> Builds OCI images without a Docker daemon — which is what makes image builds possible inside a Kubernetes pod.

## What it is

A daemonless image builder. `buildah bud` ("build using Dockerfile") consumes an ordinary Dockerfile,
including BuildKit-style `RUN --mount=type=cache`. No socket to mount, no daemon to run alongside.

## What it does here

One build step per service, generated from a single template in `.buildkite/pipeline.sh` (§12.5), plus
an explicit one for the [[backstage]] portal (§14.8). Pushes to [[sonatype-nexus]] with
`--tls-verify=false`, authenticating from a Secret that [[external-secrets-operator]] renders as a
plain `config.json`.

> [!warning] `privileged: true` is the ugliest line in the tutorial
> Building images needs mount and user-namespace operations a default-restricted container cannot
> perform. The options, honestly ranked:
> 1. **privileged** — what we do; a malicious Dockerfile can escape to the node.
> 2. **rootless Buildah** with `/etc/subuid` mapping and `seccomp: unconfined` — fiddly, version-sensitive.
> 3. **A remote BuildKit daemon** on dedicated hardware, so build pods hold no privilege — the correct
>    production answer.
> 4. **User namespaces** — genuinely safe, still stabilising in Kubernetes.
>
> If you take one thing to production: **builds run on isolated node pools, never alongside workloads.**

## Key concepts

- **`STORAGE_DRIVER=vfs`** avoids overlay-in-overlay, at a real cost in speed and disk. It is most of
  why the Backstage image build takes 20–40 minutes (§14.8).
- **`BUILDAH_FORMAT=docker`** emits Docker-format manifests, which older registries prefer.
- **`REGISTRY_AUTH_FILE`** points at the mounted auth JSON — no `docker login` needed.

## Why this, not the alternative

vs **Docker-in-Docker**: DinD needs a privileged daemon too *and* adds a daemon lifecycle to manage.
vs **Kaniko**: viable, but effectively unmaintained as of 2025. vs **BuildKit**: the best production
answer as a shared remote builder, more infrastructure than a laptop lab warrants.

## Official docs

- Site: https://buildah.io/
- `buildah bud`: https://github.com/containers/buildah/blob/main/docs/buildah-build.1.md
- Tags: https://quay.io/repository/buildah/stable?tab=tags

> [!tip] Related
> [[buildkite]], [[sonatype-nexus]], [[docker]], [[dynamic-pipelines]]

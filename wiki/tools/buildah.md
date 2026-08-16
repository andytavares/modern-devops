---
type: tool
tags: [containers, build, ci]
role: Builds and pushes OCI images inside CI pods
version: quay.io/buildah/stable:v1.40.1
docs: https://buildah.io/
date_added: 2026-08-15
date_updated: 2026-08-16
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

## Every `FROM` must be fully qualified

Docker silently assumes Docker Hub for an unqualified image name. **Buildah does not.**
`quay.io/buildah/stable` ships:

```
unqualified-search-registries = ["registry.fedoraproject.org", "registry.access.redhat.com", "docker.io"]
short-name-mode = "enforcing"
```

so `golang:1.26-alpine` is genuinely ambiguous and Buildah asks which registry you meant.

> [!warning] It hangs in CI and fails instantly on a laptop — hit 2026-08-16
> ```
> [1/2] STEP 1/7: FROM golang:1.26-alpine AS builder
> ? Please select an image:
>   ▸ registry.fedoraproject.org/golang:1.26-alpine
>     registry.access.redhat.com/golang:1.26-alpine
>     docker.io/library/golang:1.26-alpine
> ```
>
> The [[buildkite]] build pod has a TTY, so Buildah waits for an answer that never comes. Three builds
> sat for 20–29 minutes and exhausted the Buildkite concurrency limit. **Without** a TTY the same
> command fails in a second — `Error: short-name resolution enforced but cannot prompt without a TTY`
> (verified: exit 125 short-name, exit 0 fully qualified) — so it does not reproduce outside CI.
>
> **The trap is that it half-works.** `python:3.13-slim` resolved silently the whole time, because
> Buildah's bundled `/etc/containers/registries.conf.d/000-shortnames.conf` happens to alias
> `"python" = "docker.io/library/python"`. There is no alias for `golang`. That list is a convenience,
> not a contract — do not let one image's luck convince you the pattern is safe.

There is a supply-chain argument beyond the mechanics: an unqualified name is a name whose **meaning
depends on the machine resolving it**, which is precisely what [[supply-chain-choke-point]] exists to
eliminate. Pinning the registry is the same discipline as pinning the tag — see
[[immutable-image-tags]].

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

---
type: tool
tags: [containers, local-dev]
role: The container runtime the whole lab sits inside
version: "Engine / Desktop 27.x+"
docs: https://docs.docker.com/
date_added: 2026-08-15
date_updated: 2026-08-15
status: in-use
---

# Docker

> [!info] One-liner
> The local container engine — here it hosts the kind nodes, the Nexus container, and the network they share.

## What it does here

Three jobs, and only the first is the obvious one:

1. Runs [[kind]]'s nodes as containers.
2. Runs [[sonatype-nexus]] as a plain container attached to the **`kind` Docker network**, which is
   what lets cluster nodes resolve `nexus` by name (§5.2) — the single most fiddly piece of
   networking in the tutorial.
3. Holds the `insecure-registries` trust config that lets a plain-HTTP registry work at all (§5.8).

Resource allocation is a real constraint, not a formality: **CPUs ≥ 6, Memory ≥ 16 GB, Disk ≥ 80 GB**
once [[istio]] and [[backstage]] are in (§1.3).

## Key concepts

- **`insecure-registries`** is per-daemon client trust policy. Setting it is how Docker agrees to talk
  HTTP to `nexus:8082`. containerd on the kind nodes needs its own, separate config — see
  [[containerd]].
- **The daemon's image cache is not the cluster's.** Building locally does not make an image
  available to a Pod.
- Docker Desktop's VM is where "out of disk" actually happens on macOS.

## Gotchas

- Changing `insecure-registries` requires a Docker restart, and the failure mode before you do is the
  misleading `http: server gave HTTP response to HTTPS client`.
- The Nexus container's IP can change across restarts, which breaks the CoreDNS entry pods rely on
  (§5.10). Re-run that step after a Docker restart.

## Official docs

- Docs: https://docs.docker.com/
- Daemon config / insecure registries: https://docs.docker.com/reference/cli/dockerd/

> [!tip] Related
> [[kind]], [[containerd]], [[sonatype-nexus]], [[buildah]]

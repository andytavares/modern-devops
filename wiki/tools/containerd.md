---
type: tool
tags: [containers, kubernetes, runtime]
role: The container runtime inside each kind node
version: whatever the kind node image ships
docs: https://github.com/containerd/containerd/blob/main/docs/hosts.md
date_added: 2026-08-15
date_updated: 2026-08-15
status: in-use
---

# containerd

> [!info] One-liner
> The CRI runtime the kubelet actually talks to — and the thing that must be taught to trust our plain-HTTP registry.

## What it is

The container runtime Kubernetes uses via the CRI. It pulls images, manages snapshots and runs
containers. You rarely interact with it directly; you interact with its **configuration**, and in
this platform that configuration is the difference between working image pulls and a cluster-wide
`ImagePullBackOff`.

## What it does here

Every [[kind]] node runs containerd. Two edits make [[sonatype-nexus]] usable (§4.1, §5.9):

1. `containerdConfigPatches` in the kind config sets `config_path = "/etc/containerd/certs.d"`.
2. A `hosts.toml` is written into that directory per registry host, marking `nexus:8082` as plain
   HTTP (`skip_verify` / `http`).

This is the **supported** mechanism. The older `[plugins."io.containerd.grpc.v1.cri".registry.mirrors]`
block is deprecated, and copying it from an old blog post is a common way to lose an hour.

## Key concepts

- **`certs.d` is per-host directory config**, mirroring Docker's `/etc/docker/certs.d` convention.
- **Docker's trust config and containerd's are separate.** Your laptop pushing successfully says
  nothing about whether a node can pull. Verify from a node:
  `docker exec devops-worker curl -s -o /dev/null -w '%{http_code}' http://nexus:8082/v2/` → expect `401`.
- `401` is the *good* answer there: reachable and demanding auth.

## Official docs

- Registry host config (`hosts.toml`): https://github.com/containerd/containerd/blob/main/docs/hosts.md
- Project: https://containerd.io/

> [!tip] Related
> [[kind]], [[docker]], [[sonatype-nexus]], [[kubernetes]]

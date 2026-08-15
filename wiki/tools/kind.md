---
type: tool
tags: [kubernetes, local-dev]
role: The local Kubernetes cluster
version: v0.32.0
docs: https://kind.sigs.k8s.io/docs/user/quick-start/
date_added: 2026-08-15
date_updated: 2026-08-15
status: in-use
---

# kind (Kubernetes IN Docker)

> [!info] One-liner
> Runs real Kubernetes nodes as Docker containers — genuine kubelet and containerd, no VM, disposable in seconds.

## What it is

Each "node" is a Docker container running containerd and a kubelet. Because it is the real thing
rather than a simulation, node-level behaviour you'd meet in production — scheduling, image pulls,
registry trust, DaemonSets, node pressure — behaves the same way. It is a testing tool for Kubernetes
itself, which is why it stays close to upstream.

## What it does here

Creates the three-node `devops` cluster from `infra/kind-cluster.yaml` (§4.1–4.2). Three pieces of
that config are load-bearing:

1. **`containerdConfigPatches`** — points containerd at `/etc/containerd/certs.d`, so per-registry
   config for [[sonatype-nexus]] can be dropped in as `hosts.toml` files (§5.9). See [[containerd]].
2. **`extraPortMappings`** 80/443 → host — gives [[ingress-nginx]] a stable edge, so
   `*.localtest.me` URLs work in a browser without `port-forward`.
3. **`node-labels: ingress-ready=true`** on the control plane — the label the ingress DaemonSet
   selects. The cluster config and the ingress manifest have to agree, or nothing serves.

## Key concepts

- **Port mappings are fixed at create time.** Changing them means recreating the cluster. This is the
  reason the tutorial keeps [[ingress-nginx]] as the edge rather than swapping in an Istio gateway.
- **Node images are re-published under the same tag.** Pin by digest if you need reproducibility;
  omitting `image:` and taking kind's default is the safer default (§4.1).
- **The cluster is cattle.** `kind delete cluster` and rebuild is the normal repair, not a last resort.

## Why this, not the alternative

- **vs minikube** — VM drivers are heavier and the registry story is fiddlier.
- **vs k3d/k3s** — excellent, but k3s trims and substitutes components (Traefik, servicelb), so you
  learn a slightly non-standard Kubernetes. kind gives you upstream.
- **vs a cloud cluster** — costs money and hides the node.

## Gotchas

- Images must be pushed to a registry the *nodes* can reach; your laptop's Docker daemon cache is not
  the nodes' cache. Hence [[sonatype-nexus]] on the `kind` Docker network (§5.2).
- Disk pressure on the Docker VM shows up as `Pending` pods with confusing events.

## Official docs

- Quick start: https://kind.sigs.k8s.io/docs/user/quick-start/
- Releases: https://github.com/kubernetes-sigs/kind/releases

> [!tip] Related
> [[kubernetes]], [[containerd]], [[ingress-nginx]], [[docker]], [[sonatype-nexus]]

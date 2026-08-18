---
type: tool
tags: [cluster, local-development]
role: the local three-node cluster — real kubelet and containerd, in Docker
version: v0.32.0
docs: https://kind.sigs.k8s.io/docs/user/quick-start/
date_added: 2026-08-17
date_updated: 2026-08-17
status: in-use
---

# kind

> [!info] One-liner
> Kubernetes IN Docker: each node is a Docker container running a real kubelet and a real [[containerd]]. Not a simulation — the failure modes are the ones you get in a managed cluster.

## What it is

A cluster provisioner. Nodes are containers on a user-defined Docker network called `kind`.
That network is the reason [[sonatype-nexus]] can be reached by name from the nodes (§5.2).

## What it does here

`infra/kind-cluster.yaml` — three nodes, and three things a bare `kind create cluster` does not do
(§4.1):

1. **Multiple nodes**, so scheduling and node pressure behave like the real thing.
2. **`extraPortMappings`** for 80/443 on the control-plane node, so `*.localtest.me` reaches
   [[ingress-nginx]] in a browser.
3. **`containerdConfigPatches`** setting `config_path = "/etc/containerd/certs.d"`, which is what
   §5.9's per-registry `hosts.toml` files land in. The older `mirrors` config in containerd's TOML is
   deprecated.

The control plane is labelled `ingress-ready=true` via `kubeadmConfigPatches`, and §4.3 patches the
ingress controller's `nodeSelector` to require it.

## Decisions worth naming

**`extraPortMappings` over `kubectl port-forward`** (§4.1). Port mappings are fixed at cluster-create
time and cannot change without recreating the cluster — but they give stable URLs that survive pod
restarts and teach you Ingress. `port-forward` dies with the pod and teaches nothing. It is kept for
one-off debugging only, and even that stops working once STRICT mTLS is on ([[mtls]], §6.4).

**No `image:` pin.** kind ships a node image matched to its own release; omitting it is the safe
default. If you need a specific Kubernetes version, pin the **digest** from the release page — kind
re-publishes node image tags, so the tag alone is not reproducible (§4.1).

**`*.localtest.me`.** Public DNS resolves it and every subdomain to `127.0.0.1`, so you get real
hostname routing with no `/etc/hosts` edits. The one `/etc/hosts` line this platform does add is
`nexus` (§5.7), and that is because the name must mean the same thing in three resolvers.

**The Ingress Service sits at `EXTERNAL-IP <pending>` forever, and that is harmless.** Traffic arrives
via `hostPort`, not through the Service. Do not install MetalLB to "fix" it (Appendix B).

**`deleteClaim: true` on the Kafka node pools is a kind-ism** — right for a laptop, catastrophic in
production (§8.3). See [[strimzi]].

## Cost of the choice

The cluster is imperative: `kind create cluster` is a command, not a manifest, so the one thing this
platform does not GitOps is the cluster itself. Appendix C names Terraform/OpenTofu or Crossplane as
where to go next.

## Related

[[kubernetes]] · [[containerd]] · [[docker]] · [[ingress-nginx]] · [[sonatype-nexus]]

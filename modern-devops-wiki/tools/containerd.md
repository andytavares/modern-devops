---
type: tool
tags: [runtime, registry, cluster]
role: the node container runtime, and the `hosts.toml` that makes Nexus pullable
version: whatever the kind v0.32.0 node image ships
docs: https://github.com/containerd/containerd/blob/main/docs/hosts.md
date_added: 2026-08-17
date_updated: 2026-08-17
status: in-use
---

# containerd

> [!info] One-liner
> The CRI runtime on every [[kind]] node. It is the component that actually pulls your images, and therefore the one that has to be taught about [[sonatype-nexus]].

## What it does here

Two halves, and both are needed (§4.1, §5.9):

**Cluster config sets the search path.** `infra/kind-cluster.yaml` patches containerd with
`[plugins."io.containerd.grpc.v1.cri".registry] config_path = "/etc/containerd/certs.d"`.

**§5.9 populates it, on every node:**

```toml
# /etc/containerd/certs.d/nexus:8082/hosts.toml
server = "http://nexus:8082"

[host."http://nexus:8082"]
  capabilities = ["pull", "resolve"]
```

No restart is required — `config_path` directories are read **per pull**. That is the property that
makes this a config drop rather than a node reboot.

## The verification that actually proves it

```bash
docker exec devops-worker curl -s -o /dev/null -w '%{http_code}\n' http://nexus:8082/v2/
# 401  ← correct: reachable, and demanding auth
```

`401` proves DNS and routing work. `000` or a hang means the Nexus container is not on the `kind`
network. A `200` would mean anonymous Docker pull is on, which §5.4 deliberately leaves off — see
[[sonatype-nexus]].

## Why this is one of three resolvers, not one

`nexus` must mean the same thing to your shell, to containerd on the nodes, and to pods (§5.2).
containerd resolves via **Docker's embedded DNS** on the `kind` network; pods resolve via **CoreDNS**,
which knows nothing about Docker networks and needs the static-IP `hosts` entry from §5.10; your shell
resolves via `/etc/hosts`. Miss one and `nexus:8082/shop/order-api:abc123` means different things in
different places, and you get an `ImagePullBackOff` that reads like a permissions bug and is not.

## Related

[[kind]] · [[docker]] · [[sonatype-nexus]] · [[supply-chain-choke-point]]

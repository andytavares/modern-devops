---
type: tool
tags: [runtime, local-development]
role: hosts the kind nodes, the Nexus container, and the shared network
version: Engine 27.x or newer
docs: https://docs.docker.com/engine/
date_added: 2026-08-17
date_updated: 2026-08-17
status: in-use
---

# Docker

> [!info] One-liner
> The substrate. [[kind]]'s nodes are Docker containers, [[sonatype-nexus]] is a Docker container beside them, and the `kind` network is what lets the two resolve each other by name.

## What it does here

**Hosts everything.** §1.3 asks for **CPU ≥ 6, Memory ≥ 16 GB, Disk ≥ 80 GB**, and is specific about
where it goes: [[istio]] adds `istiod` (~500 MB) plus 50–100 MB of Envoy per meshed pod, and
[[backstage]]'s image build in a `vfs`-backed [[buildah]] pod transiently wants several gigabytes of
disk. At 12 GB the honest advice is to skip the mesh or run it in ambient mode.

**Runs Nexus on the `kind` network with a static IP** (§5.3):

```bash
docker run -d --name nexus --network kind --network-alias nexus --ip 172.18.255.10 \
  --restart unless-stopped -p 8081:8081 -p 8082:8082 -v nexus-data:/nexus-data \
  -e INSTALL4J_ADD_VM_PARAMS="-Xms1200m -Xmx1200m -XX:MaxDirectMemorySize=2g" \
  sonatype/nexus3:3.95.0
```

`--ip` is the load-bearing flag. The CoreDNS entry in §5.10 must name an *address*, and an address
Docker chose is an address Docker is free to choose differently on the next start. `172.18.255.10` is
high in the `kind` subnet (`172.18.0.0/16`), far from the low end where kind allocates node addresses.

**Trusts the plain-HTTP registry** (§5.8) — `"insecure-registries": ["nexus:8082"]` in Docker Engine
settings, then **restart Docker**. Without it, `docker push` fails with
`http: server gave HTTP response to HTTPS client`.

> [!warning] Plain HTTP is TLS termination by fiat
> Credentials and image layers cross the network in the clear. §5.8 says this outright: in production
> Nexus sits behind TLS with a certificate the nodes trust, and issuing a CA to containerd on three
> kind nodes is a 20-step detour this tutorial declines. The *shape* — per-registry trust policy on
> the client — is identical either way. Appendix C lists edge TLS as a known gap.

## The failure that comes back

Pods stop resolving `nexus` after a Docker restart when the container was recreated **without**
`--ip` (Appendix B). The `nexus-data` volume is separate from the container, so recreating it with the
flag loses nothing.

## Related

[[kind]] · [[containerd]] · [[sonatype-nexus]] · [[buildah]]

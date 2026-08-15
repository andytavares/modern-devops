---
type: tool
tags: [artifacts, supply-chain]
role: The artifact choke point — registry, and proxy for every dependency
version: sonatype/nexus3:3.95.0
docs: https://help.sonatype.com/en/sonatype-nexus-repository.html
date_added: 2026-08-15
date_updated: 2026-08-15
status: in-use
---

# Sonatype Nexus Repository

> [!info] One-liner
> One box that is a Docker registry *and* a PyPI proxy *and* a Go module proxy *and* an npm proxy — the single point every artifact passes through.

## What it is

An artifact repository manager. It hosts repositories you publish to (**hosted**), caches
repositories you consume from (**proxy**), and can present several as one (**group**).

The important reframe: an artifact repository is not storage, it is a **supply-chain choke point**
(§5.1). Storage is the boring part. The value is that every dependency entering the platform crosses
one boundary you control, log and can block. See [[supply-chain-choke-point]].

## What it does here

Runs as a plain [[docker]] container on the **`kind` network**, so cluster nodes can resolve `nexus`
by name (§5.2). Four repositories:

| Repo | Type | Consumed by |
|---|---|---|
| `docker-hosted` (port 8082) | hosted | [[buildah]] pushes, [[containerd]] pulls |
| `pypi-proxy` | proxy | order-api's [[uv]] / pip (§12.5 env) |
| `go-proxy` | proxy | order-worker's `GOPROXY` |
| `npm-proxy` | proxy | [[backstage]]'s yarn install (§14.2) |

Three **independent** trust configurations are required, and this is where most of the pain lives:

1. **Docker daemon** — `insecure-registries` (§5.8)
2. **containerd on each node** — `hosts.toml` (§5.9), see [[containerd]]
3. **Pods** — a CoreDNS entry mapping `nexus` to the container's Docker IP (§5.10)

Your laptop pushing successfully says nothing about whether a node can pull. Verify from a node:
`docker exec devops-worker curl -s -o /dev/null -w '%{http_code}' http://nexus:8082/v2/` → `401` is
the *good* answer (reachable, demanding auth).

## Key concepts

- **Docker Bearer Token Realm** must be activated in Security → Realms, or `docker login` returns 401
  with a correct password (§5.4).
- **The connector port (8082) is not the UI port (8081).** A Docker registry needs its own port.
- **`GOSUMDB=off` is required** behind a private Go proxy — the public checksum database is
  unreachable. That is a real reduction in integrity guarantees; the production answer is an internal
  sumdb or vendoring, not disabling verification.
- Plain HTTP here is TLS termination by fiat. Production means a certificate the nodes trust; the
  *shape* of what's configured — per-registry client trust policy — is identical either way.

## Gotchas

- The container's IP changes across Docker restarts → pods stop resolving `nexus` → re-run §5.10.
- The tutorial uses the `nx-admin` role for the CI user; scoping it down is an open question.

## Official docs

- Docs: https://help.sonatype.com/en/sonatype-nexus-repository.html
- Docker registry: https://help.sonatype.com/en/docker-registry.html
- REST API: https://help.sonatype.com/en/rest-api-index.html

## Open questions

- What is the minimum privilege set for a push-only CI user?

> [!tip] Related
> [[docker]], [[containerd]], [[buildah]], [[supply-chain-choke-point]], [[buildkite]], [[uv]], [[go]]

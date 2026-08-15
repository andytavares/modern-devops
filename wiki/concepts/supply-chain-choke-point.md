---
type: concept
tags: [security, supply-chain, artifacts]
docs: https://slsa.dev/
date_added: 2026-08-15
date_updated: 2026-08-15
---

# The supply-chain choke point

> [!info] One-liner
> An artifact repository is not storage — it is the one boundary every dependency crosses, which makes it the one place you can see, cache and block.

## The idea

Left alone, a build pulls from pypi.org, proxy.golang.org, registry.npmjs.org and Docker Hub — four
trust relationships, none of them yours, all of them reachable from your build pods. Route them
through one proxy and you get:

- **Visibility** — what actually entered, and when
- **Availability** — the build survives an upstream outage or a yanked package
- **Control** — a place to block a known-bad version, and later to scan and gate

## How it's built here

[[sonatype-nexus]] proxies PyPI, Go modules and npm, and hosts our own images (§5.1). The pipeline
sets `PIP_INDEX_URL`, `UV_INDEX_URL`, `GOPROXY` and yarn's `npmRegistryServer` so **builds never talk
to the public internet directly** (§12.5, §14.2).

## What we don't have yet, and what it would take

The choke point exists; the gate does not. Missing (Appendix C):

| Gap | Tool |
|---|---|
| SBOM per image | Syft |
| Vulnerability scanning as a build step | Grype / Trivy |
| Image signing | Cosign + Sigstore |
| Admission rejecting unsigned images | Kyverno |

That ordering is the right one: you cannot enforce a policy about artifacts you can't enumerate.

## Gotchas

- **`GOSUMDB=off`** is required behind a private Go proxy — the public checksum database is
  unreachable. That is a real reduction in integrity guarantees; production answer is an internal
  sumdb or vendoring, not disabling verification.
- A proxy is a cache, not a fork: upstream deleting a version still hurts, later.

## Official docs

- SLSA (supply-chain levels): https://slsa.dev/
- Nexus: https://help.sonatype.com/en/sonatype-nexus-repository.html

> [!tip] Related
> [[sonatype-nexus]], [[uv]], [[go]], [[buildah]], [[buildkite]]

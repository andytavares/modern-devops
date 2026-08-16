---
type: tool
tags: [artifacts, supply-chain]
role: The artifact choke point — registry, and proxy for every dependency
version: sonatype/nexus3:3.95.0
docs: https://help.sonatype.com/en/sonatype-nexus-repository.html
date_added: 2026-08-15
date_updated: 2026-08-16
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

## Why this, not the alternative

**vs JFrog Artifactory, and vs Nexus Pro** — the odd one of the three substitutions in this platform,
because it is not a substitution at the *product* level at all.

**What you get at work is Nexus Repository Pro or JFrog Artifactory.** Which one was a procurement
decision. Neither is licensable for a tutorial: JFrog lists self-managed Artifactory from
**$27,000/year** ([pricing](https://jfrog.com/pricing/), as of 2026-08) and Nexus Pro is quote-only.

**Why this teaches the same thing.** `sonatype/nexus3:3.95.0` is **Nexus Repository Community
Edition** — the same binary and UI as Pro under a usage cap of **40,000 total components or 100,000
requests per day**, after which it stops accepting new components until usage drops below both
([CE onboarding](https://help.sonatype.com/en/ce-onboarding.html), as of 2026-08). Note that failed
requests, including 401s, count toward the request limit. Everything §5 configures — hosted vs proxy vs
group, the Docker Bearer Token realm, a separate connector port, per-repository anonymous access, a
private `GOPROXY` — is identical on Pro.

It transfers to Artifactory too, because the interesting parts are protocols rather than products: OCI
distribution for the registry, PEP 503's simple index for PyPI, the Go module proxy protocol for Go. The
client-side configuration (`insecure-registries`, [[containerd]]'s `hosts.toml`, `PIP_INDEX_URL`,
`GOPROXY`, `GOSUMDB=off`) is unchanged, and the repository vocabulary maps one-to-one:

| Nexus | Artifactory |
|---|---|
| hosted | local |
| proxy | remote |
| group | virtual |
| — | federated (multi-site sync; no CE equivalent) |

**Where it genuinely does not teach the same thing.** CE has no high availability, no content
replication and no SAML/SSO, so the operational half of running a real artifact repository is out of
reach here. And the **Policy** leg of [[supply-chain-choke-point]] is aspirational in this platform:
blocking a CVE at the choke point is done by Sonatype Repository Firewall / IQ Server or JFrog Xray,
both paid add-ons. We teach where the choke point is and prove everything routes through it. We do not
teach what a policy engine attached to it feels like.

## Key concepts

- **Docker Bearer Token Realm** must be activated in Security → Realms, or `docker login` returns 401
  with a correct password (§5.4).
- **The connector port (8082) is not the UI port (8081).** A Docker registry needs its own port.
- **`GOSUMDB=off` is required** behind a private Go proxy — the public checksum database is
  unreachable. That is a real reduction in integrity guarantees; the production answer is an internal
  sumdb or vendoring, not disabling verification.
- Plain HTTP here is TLS termination by fiat. Production means a certificate the nodes trust; the
  *shape* of what's configured — per-registry client trust policy — is identical either way.

## Anonymous access: two switches, not one

Nexus gates unauthenticated reads at **two independent levels**, and conflating them breaks CI.

1. **Global** — ⚙ → Security → Anonymous Access. Off means *everything* 401s, including the language
   proxies.
2. **Per Docker repository** — *"Allow anonymous docker pull"* on the repository itself.

Sonatype is explicit that both are required for anonymous Docker pulls: *"enabling global anonymous
access is necessary, but you also need to enable a repository-level setting on each individual Docker
repository for anonymous pulls to function correctly"*
([anonymous access](https://help.sonatype.com/en/anonymous-access.html)).

**So global anonymous access does not give away `docker pull`.** Our `docker-hosted` leaves the
per-repository switch unchecked (§5.4), so the registry still demands credentials and the
[[openbao]] → [[external-secrets-operator]] → `imagePullSecret` chain in §7 keeps its whole point.

Scope it properly by trimming the default `nx-anonymous` role to
`nx-repository-view-pypi-pypi-proxy-*` and `nx-repository-view-go-go-proxy-*` — which is Sonatype's
own advice: *"modify the default anonymous role (`nx-anonymous`) to restrict access to only necessary
content"* ([users](https://help.sonatype.com/en/users.html)).

> [!warning] This was a real failure, 2026-08-15
> The tutorial said **Disable anonymous access** (§5.3) while §12.5's build steps fetch from the
> proxies with **no credentials** — `PIP_INDEX_URL` and `GOPROXY` are bare URLs. Two instructions that
> cannot both be followed. Symptoms: Go failed loudly with
> `reading http://nexus:8081/repository/go-proxy/...zip: 401 Unauthorized`, while [[uv]] **hung**
> instead of failing. Fixed by enabling global anonymous access; the tutorial now says so.
> Verify with `curl -o /dev/null -w '%{http_code}' http://nexus:8081/repository/pypi-proxy/simple/`
> → `200`.

## Gotchas

- The container's IP changes across Docker restarts → pods stop resolving `nexus` → re-run §5.10.
- The tutorial uses the `nx-admin` role for the CI user; scoping it down is an open question.
- A `404` (not `401`) on `/repository/<name>/…` means the repository does not exist yet, not that
  auth failed. Easy to misread while §5.6 is still pending.

## Official docs

- Docs: https://help.sonatype.com/en/sonatype-nexus-repository.html
- Docker registry: https://help.sonatype.com/en/docker-registry.html
- REST API: https://help.sonatype.com/en/rest-api-index.html

## Open questions

- What is the minimum privilege set for a push-only CI user?

> [!tip] Related
> [[docker]], [[containerd]], [[buildah]], [[supply-chain-choke-point]], [[buildkite]], [[uv]], [[go]]

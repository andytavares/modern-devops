---
type: tool
tags: [artifacts, registry, supply-chain]
role: registry plus PyPI/Go/npm proxies — the supply-chain choke point
version: sonatype/nexus3:3.95.0 (Community Edition)
docs: https://help.sonatype.com/en/sonatype-nexus-repository.html
date_added: 2026-08-17
date_updated: 2026-08-17
status: in-use
---

# Sonatype Nexus Repository

> [!info] One-liner
> The single point every dependency entering this platform passes through. Not storage — a control point. See [[supply-chain-choke-point]].

## What it is here

One container on the `kind` [[docker]] network (§5.3), serving four repositories:

| Repository | Type | Reached at |
|---|---|---|
| `docker-hosted` | docker (hosted) | `nexus:8082` — its **own connector port** |
| `pypi-proxy` | pypi (proxy) → pypi.org | `http://nexus:8081/repository/pypi-proxy/simple` |
| `go-proxy` | go (proxy) → proxy.golang.org | `http://nexus:8081/repository/go-proxy` |
| `npm-proxy` | npm (proxy) → registry.npmjs.org | `http://nexus:8081/repository/npm-proxy/` (§14.2) |

Docker needs its own port because the registry API is served at the root path (`/v2/`) and cannot be
nested under `/repository/<name>` the way PyPI or Maven can (§5.4). The **Docker Bearer Token Realm**
must be moved to Active or `docker login` fails with a confusing 401.

Consumers: [[pants]] (`[python-repos] indexes`, `[golang] GOPROXY`), [[uv]]
(`[[tool.uv.index]]` in `pyproject.toml`), [[buildkite]]'s `PIP_INDEX_URL`/`GOPROXY` env,
[[backstage]]'s `.yarnrc.yml` `npmRegistryServer`, and the CI image build itself.

## The networking, which is the genuinely hard part

§5.2: `nexus` must resolve to the same thing from **three** places — your shell (`/etc/hosts`,
§5.7), [[containerd]] on the nodes (Docker embedded DNS via `--network-alias`, §5.9), and pods
(CoreDNS `hosts` block naming the static IP, §5.10). The `--ip 172.18.255.10` in §5.3 is what makes
the CoreDNS entry survive the container being recreated.

## Anonymous access: narrower than it sounds

§5.3 says to **enable global anonymous access**, and it is required: CI resolves through the PyPI, Go
and npm proxies with no credentials at all, so without it every build fails on `401 Unauthorized`.

That does **not** give away `docker pull`. Nexus controls Docker anonymous pulls with a second,
**per-repository** switch — *"Allow anonymous docker pull"* on the Docker repository — which §5.4
leaves unchecked. Sonatype's docs are explicit that both are needed. So the
[[openbao]] → ExternalSecret → `imagePullSecret` chain in §7.6 keeps all of its value.

The tightening §5.3 prescribes and this repo has **not** applied: cut `nx-anonymous` down to
`nx-repository-view-pypi-pypi-proxy-*` and `nx-repository-view-go-go-proxy-*`. See
[[open-questions]].

## `nx-admin` for the CI user, flagged rather than hidden

§5.5 gives the `ci` user `nx-admin` and says so outright: the correct move is a custom role holding
`nx-repository-view-docker-docker-hosted-*` plus browse on the proxies. Appendix C calls it **the
quickest real improvement available**.

## A private Go proxy is not a reason to disable checksum verification

The widespread advice to set `GOSUMDB=off` behind a private proxy is wrong, and §5.6 is precise about
why. A `go (proxy)` repository serves modules only, not checksum-database data. Sonatype's documented
answer is a **raw (proxy)** repository pointing at `https://sum.golang.org` plus
`GOSUMDB='sum.golang.org <NEXUS_RAW_URL>'` — the database name stays, the fetch route changes.

This tutorial creates neither, and does not need to: `go.sum` records a hash for every module in the
build list, so `go` verifies locally and never consults the database during a build. The database is
consulted when a module is *added* — exactly when you want it working. For a genuinely private module
the scoped escape is `GOPRIVATE=github.com/yourorg/*`, not a global switch. Both [[go]] and [[pants]]
keep verification on.

## Community Edition: what transfers, and what does not

This is [[enterprise-substitution]] in its clearest form. `sonatype/nexus3:3.95.0` is **Nexus
Repository Community Edition** — the same binary and UI as Pro, under a usage cap of **40,000 total
components or 100,000 requests per day**, after which it refuses new components until you drop below
both (Sonatype, as of 2026-08). At work you get Nexus Pro or JFrog Artifactory, chosen by procurement;
Artifactory lists self-managed from **$27,000/year** and Nexus Pro is quote-only.

**Transfers, because the parts that matter are protocols not products.** A Docker registry is the OCI
distribution API; a PyPI proxy is PEP 503's simple index; a Go proxy is the module proxy protocol. The
client config in §5.8–§5.10 is unchanged against Artifactory, whose repository types are Nexus's under
other names: **local** = hosted, **remote** = proxy, **virtual** = group.

**Does not transfer.** CE has no high availability, no content replication and no SAML/SSO, so the
operational half of running a real artifact repository is out of scope and cannot be brought in. Nor
is the **policy** half: blocking a CVE at the choke point needs Sonatype Repository Firewall / IQ
Server or JFrog Xray, both paid. This tutorial teaches you where the choke point is. It cannot show
you a policy engine bolted onto it.

## What deliberately bypasses it

The `scie-pants` launcher, which is published only on GitHub releases ([[pants]] §17.3). §5.1 states
the rule for anything that bypasses Nexus: **pin a version and a checksum a human reviewed, in your
own repo, and fetch neither at build time.** A vendor install script that downloads `${url}.sha256`
next to the artifact detects a corrupted transfer and *cannot* detect a compromised release — whoever
replaces the artifact replaces the checksum beside it. `.buildkite/pants-ci.Dockerfile` pins both
architectures' checksums as build args and bakes the result into an image living in Nexus.

## Related

[[supply-chain-choke-point]] · [[enterprise-substitution]] · [[containerd]] · [[docker]] · [[buildkite]] · [[pants]] · [[uv]] · [[immutable-image-tags]]

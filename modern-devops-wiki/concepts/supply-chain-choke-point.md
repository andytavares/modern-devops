---
type: concept
tags: [security, supply-chain, artifacts]
date_added: 2026-08-17
date_updated: 2026-08-17
---

# The supply-chain choke point

> [!info] One-liner
> An artifact repository is not storage. It is the single point where every dependency entering your builds passes through something you control.

## What controlling it buys (§5.1)

- **Availability** — your build does not break when Docker Hub rate-limits you or PyPI has an outage.
- **Auditability** — you can answer "which builds pulled `left-pad@1.3.0`?"
- **Policy** — you can block a package the moment a CVE lands, without touching a single repo.

The third is the one this platform **cannot** demonstrate: blocking a CVE at the choke point requires
Sonatype Repository Firewall / IQ Server or JFrog Xray, both paid. [[sonatype-nexus]] Community Edition
teaches you where the choke point is and how everything routes through it. It cannot show you a policy
engine bolted onto it. Said plainly rather than sold.

## Everything routes through it

| Consumer | Route |
|---|---|
| [[pants]] | `[python-repos] indexes`, `[golang] GOPROXY` |
| [[uv]] | `[[tool.uv.index]]` in `pyproject.toml` — *in the lock*, not just in CI |
| [[buildkite]] | `PIP_INDEX_URL`, `GOPROXY` env in the generated pipeline |
| [[backstage]] | `.yarnrc.yml` `npmRegistryServer` — including inside the container build |
| [[containerd]] | `hosts.toml` per node |
| the CI image | `pip install pyyaml --index-url …` |

## The one deliberate exception, and the rule it follows

The `scie-pants` launcher is published only on GitHub releases. §5.1 states the rule for anything that
bypasses the choke point:

> **Pin a version and a checksum that a human reviewed, in your own repo, and fetch neither at build
> time.**

And the reasoning that makes the usual alternative insufficient: a vendor install script downloads
`${url}.sha256` next to the artifact and verifies one against the other. **That detects a corrupted
transfer. It cannot detect a compromised release** — whoever can replace the artifact can replace the
checksum beside it. `curl … | bash` also defaults to the *latest* version, which is not a thing anyone
reviewed.

`.buildkite/pants-ci.Dockerfile` pins both architectures' checksums as build args, verifies, and bakes
the result into an image living in Nexus. Every CI run then pulls from Nexus; the one unproxied
download is explicit, pinned and verified rather than repeated on every build. `helm` gets identical
treatment.

## Proxying is not a reason to disarm verification

The most common mistake made in the name of a private proxy is `GOSUMDB=off`. §5.6 is blunt about why
it is wrong: `go.sum` already records a hash for every module in the build list, so the `go` command
verifies **locally** and never consults the checksum database during a build. The database is consulted
when a module is *added* — exactly when you want it working. Turning it off buys nothing today and
disarms verification for the next dependency someone adds. The scoped escape for a genuinely private
module is `GOPRIVATE=github.com/yourorg/*`. See [[go]].

## The choke point applied to *time*, not location

`create-app` writes `npmMinimalAgeGate` into [[backstage]]'s `.yarnrc.yml` — refusing packages
published more recently than a given window, with `@backstage/*` exempted. Nexus controls **where** a
dependency comes from; the gate controls **how battle-tested** it is when you take it. Two orthogonal
controls on the same risk, and the second one costs nothing.

## What is still missing

Appendix C: no SBOM, no image signing, no vulnerability gate. Syft for SBOMs, Grype/Trivy as a pipeline
step, Cosign + Sigstore for signatures, Kyverno to reject unsigned images at admission.

## Related

[[sonatype-nexus]] · [[immutable-image-tags]] · [[pants]] · [[uv]] · [[go]] · [[buildkite]] · [[backstage]] · [[enterprise-substitution]]

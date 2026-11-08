---
type: concept
tags: [design-decision, tooling]
date_added: 2026-08-17
date_updated: 2026-08-17
---

# Enterprise substitution

> [!info] One-liner
> This platform is shaped like an enterprise, not a startup. Where the component a real employer hands you is behind a price tag or an account gate, it is substituted with the open-source equivalent that teaches the same lesson.

## The principle, and what it is not

Most engineers do not land on a greenfield team that picks its own tools. They land somewhere with an
artifact repository they did not choose, a secrets manager another team operates, and a narrow slice
of someone else's AWS account. So those things are here, **in those roles, with those seams**
(§0, `docs/README.md`).

**The substitution is at the *vendor* level, never the *concept* level.** Each stand-in is chosen
because its API, its vocabulary and its failure modes are the ones you will meet at work.

This was previously justified on **licensing**, which read like dodging fees around obscure tools. It
is not a licensing argument. It is a fidelity argument with a licensing constraint.

## The three substitutions

| Here | Stands in for | The gate |
|---|---|---|
| [[openbao]] | HashiCorp Vault (Enterprise) | **Licence.** Vault moved to BUSL in 2023 |
| [[sonatype-nexus]] Community Edition | Nexus Pro / JFrog Artifactory | **Price.** Artifactory self-managed from $27,000/yr; Nexus Pro quote-only |
| [[floci]] | LocalStack Pro | **Price + account.** $39–89/developer/month; the free Hobby tier is non-commercial and needs an account |

*(as of 2026-08)*

## What actually transfers is protocols, not products

- **Nexus/Artifactory** — a Docker registry is the OCI distribution API; a PyPI proxy is PEP 503's
  simple index; a Go proxy is the module proxy protocol. Even the repository *types* map: Artifactory's
  local/remote/virtual are Nexus's hosted/proxy/group.
- **OpenBao/Vault** — paths, ACL policy documents, KV v2's `/data/`–`/metadata/` split, the Kubernetes
  auth method and its TokenReview dependency, tokens and leases, the CLI verbs. The concrete proof:
  [[external-secrets-operator]] configures OpenBao through its **`vault` provider**.
- **Floci/LocalStack** — SigV4 signing, SDK behaviour, pagination, path-style S3 addressing, and the
  fact that pointing an SDK at an emulator is one environment variable rather than a code branch.

## Where each one stops, stated outright

The discipline that makes this honest is that the section introducing each substitute says where the
swap stops being equivalent, rather than selling it:

- **Nexus CE** — no HA, no content replication, no SAML/SSO, so the *operational* half of running a
  real artifact repository is out of scope and cannot be brought in. And the **policy** half —
  blocking a CVE at the choke point — needs Repository Firewall / IQ Server or Xray, both paid. See
  [[supply-chain-choke-point]].
- **OpenBao** — Vault *Community* is free to run, so "we picked OpenBao because Vault costs money"
  would be a lie. The invoice is one level up, and that is the real gap: Sentinel policy-as-code,
  performance and DR replication, HSM auto-unseal and seal wrapping, control groups. Neither Vault CE
  nor OpenBao has them, so this tutorial teaches none of them.
- **Floci** — the repo dates from February 2026, so there is no track record, and you should expect to
  meet LocalStack at work. More importantly it does **not** emulate IAM policy evaluation: credentials
  are accepted and never authorised, so nothing here teaches you whether your IAM policy is correct.

> **That last one is the only place the principle leaves a genuine *teaching* gap rather than a
> licensing one.** A reader finishes this tutorial having never tested an IAM policy. See
> [[open-questions]].

## The same reasoning applied elsewhere

[[buildkite]]'s control plane is SaaS, and §12.1 says so plainly rather than pretending: **there is no
offline Buildkite.** Every other component runs on your laptop; this one does not. The stated
substitution for an air-gapped lab is Woodpecker CI or Concourse, and the note that the pipeline
*shape* is portable while the YAML dialect is not.

## Related

[[openbao]] · [[sonatype-nexus]] · [[floci]] · [[supply-chain-choke-point]] · [[buildkite]] · [[secrets-management]]

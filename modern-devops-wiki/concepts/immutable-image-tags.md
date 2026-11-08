---
type: concept
tags: [delivery, security, supply-chain]
date_added: 2026-08-17
date_updated: 2026-08-17
---

# Immutable image tags

> [!info] One-liner
> The image tag is the 12-character commit SHA, never `latest`. That single rule is what makes "what is running?" and "what is in git?" the same question.

## Why it is a correctness property

`latest` is a mutable pointer. Two clusters can run different code while both claim to run `latest`,
and rollback is undefined — you cannot roll back to a name that has since come to mean something else.
With the SHA, the image tag, the git commit and the running version are one string. **That property is
the whole point of the tutorial** (§15.3).

## Why it is also a security property

If `order-api:abc123` can change meaning, then "the git SHA in my manifest" no longer identifies a
build. An attacker who can push over an existing tag has changed what is deployed **without changing
anything reviewable.** [[gitops]] rests entirely on the tag being a stable reference to a specific
artifact.

## Where the rule is enforced, and where it is knowingly relaxed

**Enforced.** `.buildkite/pipeline.sh` resolves `BUILDKITE_COMMIT` — which a hand-triggered build sets
to the literal string `"HEAD"` — into a real SHA, and then **refuses to build at all** if the result is
not hex. Without that guard, a UI-triggered build tags images `:HEAD`: a mutable tag meaning a
different image on every build.

**Relaxed, and flagged.** `docker-hosted` in [[sonatype-nexus]] is created with `Allow redeploy`, so
you can re-run a failed step without fighting the registry. §5.4 is explicit that production is
`Disable redeploy`. Nothing depends on the mutability, because every image is still SHA-tagged.

## No convenience `latest` alongside it

§12.5 argues this out rather than asserting it. A `latest` beside the SHA is not free: it is a second,
**mutable** name for the same digest, and it is the one a human reaches for at 3am. It also contradicts
the guard at the top of the script. **Either the rule holds for every tag the pipeline writes or it is
not a rule.** If you want a human-readable pointer, resolve it at read time — `git log`, the Argo CD UI
— rather than minting one in the registry.

## The same rule applied to a CI image

`.buildkite/pants-ci.Dockerfile` is tagged `0.13.2-2`: the scie-pants version plus a **build
revision**. The revision is not decoration — the pipeline pins the tag, so anything added to the image
(helm, pyyaml, a Go bump) is a new tag and a matching edit to `pipeline.sh`. Rebuilding over the
existing tag would make it mutable, and the failure it produces is *a step that worked yesterday
failing today with `helm: not found`.*

## And to node images

kind **re-publishes node image tags**, so pinning a kind node image by tag is not reproducible. Pin
the digest (§4.1). Same class of mistake, different registry.

## Related

[[gitops]] · [[buildkite]] · [[sonatype-nexus]] · [[argo-cd]] · [[supply-chain-choke-point]] · [[kind]]

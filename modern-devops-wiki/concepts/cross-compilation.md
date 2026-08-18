---
type: concept
tags: [build-system, packaging, containers]
date_added: 2026-08-17
date_updated: 2026-08-17
---

# Building on one machine, running on another

> [!info] One-liner
> The laptop is macOS/arm64; the cluster is linux/arm64. Every artifact this repo ships has been broken at least once by that gap, and each break passed every check before failing at container start.

## The shared shape

Three distinct instances, one failure pattern: **the artifact builds, tests pass, the push succeeds,
and the container dies on start** — often before any application log line exists.

| Artifact | The flag | The failure |
|---|---|---|
| [[pex]] Python services | `complete_platforms` | resolves **macOS wheels**; fails to import in the container |
| [[go]] `order-worker` | `[golang] cgo_enabled = false` | `exec /order-worker: no such file or directory` on a file that is present and executable |
| CI image | `TARGETARCH` + per-arch checksums | bare `Exec format error` on the other architecture |

## Native extensions and `complete_platforms`

`grpcio`, `pydantic-core`, `uvloop` and `watchfiles` are all native. Without `complete_platforms`,
`pants package` resolves for the **build host**. Generate the platform description from a real
container rather than writing it by hand:

```bash
docker run --rm python:3.13-slim sh -c \
  'pip install pex && pex3 interpreter inspect --markers --tags' > 3rdparty/python/linux.json
```

Verify: `unzip -l dist/pricing.pex | grep -E 'manylinux|macosx'` — you want `manylinux2014_aarch64`.

> The constraint that follows: every platform-specific dependency must exist as a **prebuilt wheel**
> for the target, because Pants can only build sdists for the local machine. A source-only dependency
> for `linux/aarch64` cannot be cross-packaged; you would build the wheel yourself and host it in
> [[sonatype-nexus]].

## The missing loader, which reads as a missing binary

`gcr.io/distroless/static-debian12` has neither libc nor a dynamic loader. A cgo-linked Go binary needs
`/lib/ld-linux-aarch64.so.1`, and its absence produces `exec … no such file or directory` **about the
loader, not about the binary.** That message is why the bug reads as "the COPY didn't work".

```bash
readelf -l <binary> | grep interpreter   # a static binary has no PT_INTERP
```

The hand-written Dockerfile set `CGO_ENABLED=0`. **Moving the build into [[pants]] silently dropped it**,
because Pants defaults `cgo_enabled` to *true*. Same class of mistake as putting a `CGO_ENABLED=1`
binary in `scratch` — and the reason [[franz-go]] was chosen over a librdkafka wrapper in the first
place.

## Multi-arch is not optional for the CI image

`.buildkite/pants-ci.Dockerfile` re-declares `ARG TARGETARCH` per stage (BuildKit's automatic platform
arg is not visible otherwise), falls back to `dpkg --print-architecture` for the legacy builder, and
pins a **separate checksum per architecture**. An unrecognised architecture is a **build failure, not
an unverified download** — the arch selects *which* pinned checksum applies, never *whether* one does.
See [[supply-chain-choke-point]].

## Where the pattern does not apply, and why that is worth saying

The [[vite]] frontend builds inside its own Dockerfile rather than consuming a Pants artifact, because
**a static bundle is platform-independent** — none of the above can happen to it, so the artifact
handoff buys nothing.

§19.4 records that inconsistency rather than smoothing it over, on the grounds that **an unexplained
inconsistency is how the next person concludes the pattern does not matter.**

## The meta-lesson

**Dry-run validates schema, not whether the process can start.** Every one of these passes
`helm template`, `kubectl apply --dry-run=server`, `helm lint` and the test suite. The only thing that
catches them is running the container on the target architecture — which is the argument for doing so
before the cluster does.

## Related

[[pex]] · [[go]] · [[pants]] · [[franz-go]] · [[vite]] · [[supply-chain-choke-point]] · [[buildah]]

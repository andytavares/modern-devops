---
type: tool
tags: [packaging, python, build-system]
role: Python services as one executable zip, so the image is FROM plus COPY
version: produced by pants 2.33.0's `pex_binary` target
docs: https://docs.pex-tool.org/
date_added: 2026-08-17
date_updated: 2026-08-17
status: in-use
---

# PEX

> [!info] One-liner
> A single executable zip containing your code and its entire dependency closure. `python order-api.pex` runs it; there is no `pip install` at any point after [[pants]].

## The payoff

```dockerfile
# syntax=docker/dockerfile:1.7
FROM docker.io/library/python:3.13-slim
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin appuser
WORKDIR /app
COPY --chown=10001:10001 pricing.pex /app/pricing.pex
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
USER 10001
EXPOSE 50051 9090
ENTRYPOINT ["python", "/app/pricing.pex"]
```

No `uv sync`, no layer-caching strategy, no index configuration, **no build-time network access at
all**. Compare with §3.1's multi-stage Dockerfile and the argument makes itself. It is also why the
privileged [[buildah]] pod now copies a file instead of resolving a dependency tree.

## `complete_platforms` is the flag that decides whether it runs

```python
pex_binary(
    name="bin",
    tags=["deployable"],
    entry_point="pricing/main.py:main",
    dependencies=[":lib"],
    complete_platforms=["3rdparty/python:linux-platform"],
    output_path="pricing.pex",
)
```

The cluster is `linux/aarch64`; the laptop is not. `grpcio`, `pydantic-core`, `uvloop` and `watchfiles`
are all native extensions. Without `complete_platforms`, `pants package` resolves **macOS wheels** into
an artifact that builds, tests and pushes cleanly and then fails to import inside the container.

Generate the platform description from a real container rather than writing it by hand:

```bash
docker run --rm python:3.13-slim sh -c \
  'pip install pex && pex3 interpreter inspect --markers --tags' > 3rdparty/python/linux.json
```

Check the result: `unzip -l dist/pricing.pex | grep -E 'manylinux|macosx'` — you want
`manylinux2014_aarch64`, not `macosx`.

**It goes on every `pex_binary` in the repo, including the one the [[backstage]] skeleton emits.**

> One constraint follows: every platform-specific dependency must be available as a **prebuilt wheel**
> for the target — Pants can only build sdists for the local machine. A source-only dependency for
> `linux/aarch64` cannot be cross-packaged; you would build the wheel yourself and host it in
> [[sonatype-nexus]]. Not a Pants quirk — any tool resolving wheels on the build host has it, and it is
> the same class of mistake as [[cross-compilation]]'s `CGO_ENABLED=1` into `scratch`.

`output_path` puts the artifact at `dist/pricing.pex` rather than `dist/services.pricing/bin.pex`,
which is what lets `dist/` be used directly as the Buildah build context.

## A PEX needs somewhere to write (§19.3)

> [!warning] `readOnlyRootFilesystem: true` gives it nowhere, and there are no logs
> A PEX **unpacks its dependency closure on first run**. The bootstrap extracts wheels to `PEX_ROOT`,
> which must be writable, and falls back to the temp directory when it is not — so under a read-only
> root every candidate fails and the process dies **before importing a line of your code**. None of
> your logging configuration has run, so `kubectl logs` shows nothing at all:
> `FileNotFoundError: No usable temporary directory found`.

Both halves are required, on every PEX service:

```yaml
volumeMounts: [{ name: tmp, mountPath: /tmp }]
volumes:      [{ name: tmp, emptyDir: {} }]
```

plus `PEX_ROOT: "/tmp/pex"` — set **explicitly**, because the fallback order is an implementation
detail and an explicit path is a thing a reader can find. `order-api` and `pricing` take it from their
ConfigMaps; a scaffolded service takes it from an `ENV` in the skeleton's Dockerfile. All three
Deployments carry the emptyDir, so a service arriving through a [[paved-paths]] template gets both
without anyone remembering to ask.

Same class of problem as `nginx-unprivileged` needing writable `/tmp`, `/var/cache/nginx` and
`/var/run`: both render perfectly under `helm template`, pass `kubectl apply --dry-run=server`, and
fail only at runtime. **Dry-run validates schema, not whether the process can start.**

## Related

[[pants]] · [[cross-compilation]] · [[buildah]] · [[order-platform]] · [[fastapi]] · [[grpc]]

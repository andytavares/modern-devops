---
type: tool
tags: [python, packaging, containers]
role: Python application packaging — one executable zip per service
version: bundled with Pants 2.33.0
docs: https://docs.pex-tool.org/
date_added: 2026-08-16
date_updated: 2026-08-16
status: in-use
---

# PEX

> [!info] One-liner
> A single executable zip containing your code and its entire dependency closure, which turns a Python service image into `FROM python:3.13-slim` plus one `COPY`.

## What it is

**P**ython **EX**ecutable: a zip with a bootstrap that puts a resolved dependency set on
`sys.path` and runs an entry point. `python order-api.pex` works with no virtualenv, no
`pip install`, and no index configuration at runtime. [[pants]] builds them via the `pex_binary`
target; Pex is also a standalone tool.

The important mechanical detail, and the source of the failure below: **a PEX is not executed in
place.** On first run the bootstrap extracts its wheels into a cache directory, `PEX_ROOT`.

## What it does here

`services/order-api` and `services/pricing` ship as `dist/order-api.pex` and `dist/pricing.pex`
(§19.2). `pants package` builds them in the CI verify step, and the [[buildah]] pods download them as
build artifacts and copy them into an image — so the privileged build pod resolves nothing from a
network. Every service Dockerfile under `services/` is now four meaningful lines.

`output_path="pricing.pex"` on each target lands the artifact at a predictable name, which is what
lets `dist/` be the Buildah build context.

## `complete_platforms` is not optional here

> [!warning] Without it the PEX builds clean, passes every check, and dies on import in the container — hit 2026-08-16
> By default Pants builds a PEX for the **local** machine's architecture, OS and interpreter. On a
> macOS laptop that means macOS wheels — and `grpcio`, `pydantic-core`, `uvloop` and `watchfiles` are
> all native extensions. Nothing local tells you: it builds, `pants test` passes, the image builds,
> the push succeeds. The failure is an `ImportError` at container start, at maximum distance from the
> cause.
>
> Describe the target platform explicitly, generated from a real container rather than written by
> hand:
>
> ```bash
> docker run --rm python:3.13-slim sh -c \
>   'pip install pex && pex3 interpreter inspect --markers --tags' > 3rdparty/python/linux.json
> ```
>
> ```python
> file(name="linux-platform", source="linux.json")
>
> pex_binary(..., complete_platforms=["3rdparty/python:linux-platform"])
> ```
>
> Reference it from **every** `pex_binary`. Verify by unzipping — you want `manylinux2014_aarch64` in
> the wheel names, not `macosx`:
>
> ```bash
> unzip -l dist/pricing.pex | grep -E 'manylinux|macosx' | head
> ```
>
> **Why this did not bite before the [[pants]] migration:** the old Dockerfile ran `uv sync` *inside*
> a `linux/arm64` container, where the question could not arise. Moving the resolve to the build host
> is what created it.

A constraint that follows, per Pants' own docs: when building for a non-local platform, **every
platform-specific dependency must be available as a prebuilt wheel** for that target. Pants can only
build sdists for the local machine. A source-only dependency cannot be cross-packaged at all — you
would have to build the wheel yourself and host it in [[sonatype-nexus]].

## `PEX_ROOT` and `readOnlyRootFilesystem`

> [!warning] A PEX needs somewhere writable, and a hardened pod spec gives it nowhere — hit 2026-08-16
> ```
> FileNotFoundError: [Errno 2] No usable temporary directory found in
> ['/tmp', '/var/tmp', '/usr/tmp', '/app']
> ```
> Pex documents `PEX_ROOT` as defaulting to `~/.cache/pex` and as needing to be writable for
> extracting wheels on first run; it falls back to the temp directory when it is not. Under
> `readOnlyRootFilesystem: true` every candidate fails.
>
> **The failure is in the PEX bootstrap, before any application code runs**, so none of your logging
> configuration has executed and not one of your log lines appears in `kubectl logs`. It reads as a
> broken image rather than a pod spec that is one `emptyDir` short.
>
> The fix keeps the root filesystem read-only:
>
> ```yaml
>           env:
>             - name: PEX_ROOT
>               value: "/tmp/pex"
>           securityContext:
>             readOnlyRootFilesystem: true
>           volumeMounts:
>             - { name: tmp, mountPath: /tmp }
>       volumes:
>         - { name: tmp, emptyDir: {} }
> ```
>
> Set `PEX_ROOT` explicitly rather than relying on `/tmp` being writable — the fallback order is an
> implementation detail, and an explicit path is a thing the next reader can find.
>
> **Every service moving to PEX packaging inherits this.** It is the same class of problem as
> `nginx-unprivileged` needing writable `/tmp`, `/var/cache/nginx` and `/var/run`: both render
> perfectly under `helm template` and pass `kubectl apply --dry-run=server`, and fail only at runtime.
> **Dry-run validates schema, not whether the process can start.**

There is a real cost here worth naming: first-run extraction is startup latency on every fresh pod,
because an `emptyDir` starts empty. For a service with a large native closure that is seconds, not
milliseconds, and it lands inside your readiness probe budget. Pex's `--venv` / zipapp-vs-venv modes
trade image size against that latency; we have not needed to tune it.

## Key concepts

- **The closure is resolved at build time, from the lockfile.** Runtime has no index, no network, no
  resolver — which is most of the supply-chain argument for doing it this way.
- **One artifact per entry point**, named by `output_path`.
- **`python foo.pex`** rather than `./foo.pex` in the `ENTRYPOINT`, so the interpreter is the image's
  and is explicit.

## Why this, not the alternative

vs **`pip install -r requirements.txt` in the Dockerfile** (what [[uv]] did): resolves at image-build
time inside a privileged [[buildah]] pod, over the network, on every build. The PEX moves that work
to one CI step that already has a toolchain.
vs **a wheel plus a venv in the image**: roughly equivalent outcome, more moving parts, and no
single-file artifact to hand between CI steps.
vs **shiv / zipapp**: same idea, smaller feature set; PEX is what Pants produces natively.

## Official docs

- Docs: https://docs.pex-tool.org/
- Building PEX files and `--complete-platform`: https://docs.pex-tool.org/buildingpex.html
- Environment variables (`PEX_ROOT`): https://docs.pex-tool.org/api/vars.html
- Pants' PEX page: https://www.pantsbuild.org/stable/docs/python/overview/pex

> [!tip] Related
> [[pants]], [[uv]], [[buildah]], [[docker]], [[fastapi]], [[order-platform]], [[sonatype-nexus]]

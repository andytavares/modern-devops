---
type: tool
tags: [build-system, monorepo, ci]
role: one build system for Python, Go and TypeScript
version: 2.33.0, via scie-pants launcher 0.13.2
docs: https://www.pantsbuild.org/stable/docs
date_added: 2026-08-17
date_updated: 2026-08-17
status: in-use
---

# Pants

> [!info] One-liner
> `pants lint check test ::` runs ruff over Python, `go vet` over Go, mypy over both Python services *including generated protobuf stubs*, and every test suite in the repo. Adding a fourth language is a line in `backend_packages`, not a new CI step.

## The honest case against adopting it (§17.1)

A monorepo build system is a large, opinionated dependency every developer must install and every CI
job must bootstrap. With one service in one language it is **pure overhead and [[uv]] is the better
answer**. Do not adopt it because it is sophisticated. Adopt it when you can name what it fixes.

Here there are three, and all are consequences of earlier phases:

| Problem | Created by | What Pants does |
|---|---|---|
| One CI step per language, hand-edited per service | §12.5 | One command that discovers targets |
| No shared contract between order-api and order-worker | §3 | One `.proto` generating both, checked together — see [[grpc]] |
| Image builds resolving dependencies inside a privileged [[buildah]] pod | §12.5 | Artifacts built upstream; the image is `FROM` plus `COPY` |

The third is a **security** argument. The Buildah pod used to resolve a dependency tree from a network
index; now it copies a file.

## Pants and not Bazel

Bazel is better known and more powerful, and is a build system you write build files *for*, in a
language of its own, for every target — `rules_python`, a `pip_parse` repository rule, a `py_binary`
per entry point, all by hand. **Pants infers dependencies from imports**: it reads the source,
resolves `from shop.v1 import pricing_pb2` to the target that generates it, and builds the graph
without being told. That is why the `BUILD` files here are eight lines rather than eighty. The cost is
that inference is a heuristic and occasionally wrong. See [[dependency-inference]].

## Backend maturity, stated up front (§17.2)

**Five of the eight backends this repo depends on are `experimental.*`** in 2.33.0: ruff check, ruff
format, go, protobuf-go, javascript, typescript. (`pants.backend.python`,
`pants.backend.python.typecheck.mypy` and `pants.backend.codegen.protobuf.python` are stable.)

That is a real risk taken knowingly: the entire value of a polyglot monorepo is one tool building
everything, so refusing the experimental backends means not doing this. The mitigation is that **every
one has a one-command escape hatch** — `go build`, `npm run build`, `ruff check` — because Pants
delegates to the language's own toolchain rather than reimplementing it. If a backend breaks on
upgrade you lose orchestration, not the ability to ship. See [[open-questions]].

## Installation is not `pip install`

**Pants 2.x is not on PyPI.** The package stops at 2.18 on the public index. It ships as `scie-pants`,
a self-bootstrapping launcher that reads `pants_version` from `pants.toml` and fetches the matching
Pants itself.

That launcher is the **one binary in this platform that comes from outside the
[[supply-chain-choke-point]]**, deliberately and once — checksum-verified, both architectures pinned as
build args in `.buildkite/pants-ci.Dockerfile`, and baked into an image that lives in
[[sonatype-nexus]]. Not `curl … | bash`: the vendor script downloads `${url}.sha256` from the same
origin as the binary, which catches a corrupted transfer and cannot catch a compromised release.

## `pants.toml`, the non-obvious lines

- **`[golang] cgo_enabled = false` is mandatory.** Pants defaults it to **true**, linking order-worker
  dynamically against libc. `gcr.io/distroless/static-debian12` has neither libc nor a loader, so the
  pod dies with `exec /order-worker: no such file or directory` on a file that is present and
  executable. Moving the build into Pants silently dropped what the hand-written Dockerfile set. See
  [[cross-compilation]].
- **`[python-repos] indexes` and `[golang] GOPROXY` both point at Nexus**, and nothing else is
  overridden — checksum verification stays on for both languages.
- **`enable_resolves` with one named lockfile** (`locks/python-default.lock`). One lock, one
  resolution, no chance of two services disagreeing about `protobuf`. Pants still computes per-target
  dependencies from imports, so **one requirements file does not mean one fat artifact**.
- **`[python-bootstrap] search_path` names the Homebrew path explicitly.** `brew install python@3.13`
  puts the unversioned `python` in `libexec/bin`, deliberately off `PATH`. `<PYENV>` and `<PATH>` are
  the defaults and must be **repeated, not replaced**.
- **`[python-protobuf] generate_type_stubs = true`** — see [[mypy]].
- **`pants_ignore` excludes `/deploy/backstage/templates`** (the skeleton's `BUILD` contains nunjucks
  placeholders and is not valid Python until [[backstage]] renders it — Pants would fail the whole repo
  with a `BuildFileSyntaxError`), `/portal`, `/wiki`, `/raw`, and `/frontend/node_modules` +
  `/frontend/dist`. That last pair is listed because **Pants honours only the root `.gitignore`** —
  `--pants-ignore-use-gitignore` does not descend into nested ignore files, so `frontend/.gitignore`
  never reaches Pants and `tailor` walks into installed packages.
- **`/docs` is deliberately not ignored**, because `checks/` reads the phase files.
- **`[source] root_patterns = ["/", "/services/*", "/protos"]`** — see the trap below.

## Source roots, and the duplicate-module trap (§17.4)

`/services/*` makes each service directory its own import root, so
`services/order-api/order_api/main.py` is importable as `order_api.main`. `/protos` makes generated
code importable as `shop.v1.pricing_pb2` rather than by a path that leaks the layout — and a path is a
thing that changes when someone reorganises a directory.

**Every service needs a unique top-level package name.** A shared `/services/*` root puts them all in
one module namespace, so two services shipping code in `app/` — the FastAPI tutorial convention —
become the same module `app`. mypy does not degrade there, it **refuses to run** (`Duplicate module
named "app"`), and Pants cannot infer intra-service imports either, because `from app.settings import
settings` is genuinely ambiguous.

Hence `order_api/`, `pricing/`, and the Backstage skeleton templating
`${{ values.name | replace('-', '_') }}`. Underscores, not hyphens.

## Commands worth knowing

```bash
pants lint check test ::                              # everything
pants list ::                                         # every target Pants knows about
pants dependencies --transitive services/order-api:bin
pants package services/pricing:bin
pants export-codegen protos/shop/v1:protos            # read the generated code
pants generate-lockfiles --resolve=python-default
pants run services/order-api:dump-openapi > services/order-api/openapi.json
```

`pants dependencies` is what to reach for when something behaves as if a file is missing: it prints
the graph Pants **actually built**, rather than the one you assumed from reading imports.

## In CI (§19.5)

One step, running the prebuilt `nexus:8082/ci/pants:0.13.2-2` image:

- **`update-build-files --check` runs in the same invocation as `lint check test`** — it reformats
  every `BUILD` file in memory and fails when the result differs from what is committed. Pants'
  documented CI check for BUILD-file drift.
- **`--tag=deployable` selects the package set.** `::` is every target; the tag narrows it to the ones
  that ship an artifact. The alternative — globbing `services/*/BUILD` into `:bin` targets — encodes a
  naming convention in a shell pipeline where nothing checks it. With the tag, a target declares itself
  deployable in the file that already describes it, so the [[paved-paths]] scaffolder adds a service CI
  packages **without CI knowing it exists.**
- **`checks/verify_doc_listings.py` and `verify_chart.py` run as plain scripts, not Pants tests** —
  they read the whole checkout, and a Pants sandbox holds only declared dependencies. They still need
  owning targets or `pants tailor --check` reports them unowned.

The CI image also carries a Go toolchain, because **Pants searches for `go`, it does not download
one** — `pants lint ::` dies with "Cannot find any `go` binaries" otherwise — plus `unzip`/`zip`/`xz`
for unpacking the tools it *does* download (protoc, ruff, the Go SDK), a checksum-verified `helm`, and
`pyyaml` from the Nexus proxy.

## Related

[[pex]] · [[grpc]] · [[mypy]] · [[go]] · [[vite]] · [[uv]] · [[dependency-inference]] · [[cross-compilation]] · [[buildkite]] · [[buildah]] · [[sonatype-nexus]]

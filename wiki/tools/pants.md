---
type: tool
tags: [build, monorepo, python, go, typescript, ci]
role: The monorepo build system — one command for Python, Go and TypeScript
version: 2.33.0
docs: https://www.pantsbuild.org/
date_added: 2026-08-16
date_updated: 2026-08-16
status: in-use
---

# Pants

> [!info] One-liner
> A monorepo build system that infers the dependency graph from your imports, so one command lints, typechecks, tests and packages every language in the repo.

## What it is

A build orchestrator, not a compiler. Pants does not reimplement `go build`, `ruff` or `tsc` — it
works out *what* needs running, on *which* files, with *which* dependencies, and then runs the real
tool in a sandbox with only those inputs. That hermetic sandbox is what makes its caching and
parallelism trustworthy, and it is also what causes the class of failure where something works
outside Pants and not inside it: the sandbox genuinely does not contain the file you forgot to
declare.

Its distinguishing feature against the obvious alternative is **dependency inference**. Pants reads
the source, resolves `from shop.v1 import pricing_pb2` to the target that generates it, and builds
the graph without being told.

## What it does here

Replaced [[uv]] as the build path for `services/order-api`, absorbed `services/order-worker`'s
`go build`, added `services/pricing`, and builds the [[vite]] frontend (§17). Two per-language CI
steps collapsed into one `pants lint check test ::` that needs no edit when a language is added
(§19.5).

The three deployable artifacts are produced by `pants package` in CI and handed to [[buildah]] as
files, so the privileged build pod resolves nothing from a network (§19.5). See [[pex]].

`pants.toml` points `[python-repos]` and `[golang]` at [[sonatype-nexus]], and Pants itself is
installed with `pip install pantsbuild.pants==2.33.0` from the Nexus PyPI proxy rather than the
documented `curl … | bash` launcher — so the build system crosses the same
[[supply-chain-choke-point]] as everything it builds.

## Backend maturity — five of eight are experimental

As of Pants 2.33.0 / 2026-08:

| Backend | Status |
|---|---|
| `pants.backend.python` | stable |
| `pants.backend.python.typecheck.mypy` | stable |
| `pants.backend.codegen.protobuf.python` | stable |
| `pants.backend.experimental.python.lint.ruff.check` / `.format` | experimental |
| `pants.backend.experimental.go` | experimental |
| `pants.backend.experimental.codegen.protobuf.go` | experimental |
| `pants.backend.experimental.javascript` | experimental |
| `pants.backend.experimental.typescript` | experimental |

Taken knowingly. The value of a polyglot monorepo is that one tool builds everything, so refusing the
experimental backends means not doing it. The mitigation is that each delegates to the language's own
toolchain, so the escape hatch is one command — `go build`, `npm run build`, `ruff check`. A broken
backend costs orchestration, not the ability to ship.

> [!warning] In 2.33 the ruff backend path fails as a `ModuleNotFoundError`, not as "unknown backend" — hit 2026-08-16
> It is `pants.backend.experimental.python.lint.ruff.check` / `.format`, **not**
> `pants.backend.python.lint.ruff.*`. The non-experimental path is not absent: it exists on disk as a
> directory with `rules.py` and **no `register.py`**, so Pants tries to import a non-backend and dies
> with:
>
> ```
> ModuleNotFoundError: No module named 'pants.backend.python.lint.ruff.register'
> ```
>
> which reads as a broken install rather than a config typo.
>
> Also: `[ruff]` takes **no** `install_from_resolve` — ruff ships as a downloaded binary, not a
> resolved package, so it is not in the lockfile and does not want to be. `[mypy]` is the opposite and
> *does* take it. Two linters, two mechanisms.

> [!warning] `brew install python@3.13` is invisible to Pants' interpreter search — hit 2026-08-16
> ```
> No working interpreter compatible with the requested constraints was found
> ```
> with a valid CPython 3.13 installed. Homebrew puts the unversioned `python` in `libexec/bin`, which
> is deliberately not on `PATH`. The message names the constraint, which sends you to
> `interpreter_constraints` — the wrong setting entirely. Fix:
>
> ```toml
> [python-bootstrap]
> search_path = ["<PYENV>", "<PATH>", "/opt/homebrew/opt/python@3.13/libexec/bin"]
> ```
>
> `<PYENV>` and `<PATH>` are the defaults and must be repeated, not replaced.

## Source roots decide your package names

`root_patterns = ["/", "/services/*", "/protos"]`. Each service directory is its own import root, and
`/protos` makes generated code importable as `shop.v1.pricing_pb2` rather than by a path that leaks
the directory layout.

> [!warning] Every service with a top-level `app` package collides — hit 2026-08-16
> ```
> Duplicate module named "app"
> ```
> mypy does not degrade; it declines to run at all, and Pants cannot infer intra-service imports
> because `from app.settings import settings` is genuinely ambiguous. Fixed by renaming `app/` →
> `order_api/` and `app/` → `pricing/`.
>
> **This is a property of the source-root layout, not of those services.** If each service is its own
> source root, each needs a unique top-level package name — and the FastAPI convention that every
> project has an `app` is exactly wrong at more than one project. The [[backstage]] skeleton emitted
> `app/` too, making the paved path a machine for producing this failure; it now templates
> `${{ values.name | replace("-", "_") }}`.

## Key concepts

- **`::` means every target in the repo.** `pants lint check test ::` is the whole CI step.
- **One resolve, one lockfile.** `enable_resolves = true` with `locks/python-default.lock` means no
  two services can disagree about `protobuf`. Per-target dependencies are still computed from
  imports, so one requirements file does not mean one fat artifact.
- **`pants dependencies --transitive <target>`** prints the graph Pants actually built. It is the
  first thing to run when something behaves as if a file is missing.
- **`pants export-codegen`** materialises generated sources for reading. Normal goals generate into a
  sandbox on demand; you do not commit generated code.
- **`generate_type_stubs = true`** under `[python-protobuf]` — see [[grpc]] for why mypy needs it.

> [!warning] Inference does not cover a build script's inputs — hit 2026-08-16
> Pants' JS/TS backend infers from **imports**, and a build script's config files and assets are not
> imports. `tsconfig.json`, `vite.config.ts`, `index.html` and `src/style.css` all had to be declared
> by hand as `file` / `resource` targets in `frontend/BUILD`. The missing `style.css` produced **no
> error at all** — Vite built successfully in a sandbox without it and emitted an unstyled page. A
> green build and a broken page. **For any non-Python target, enumerate the inputs explicitly.**

## Why this, not the alternative

vs **[[uv]]**: uv is the better answer for one service in one language, and was ours until there were
three services and a shared `.proto`. uv has no notion of a Go target or a cross-language check.
vs **Bazel**: more powerful and far better known, but you write build files by hand for every target
— `rules_python`, a `pip_parse` repo rule, a `py_binary` per entry point. Pants' inference is why the
`BUILD` files here are eight lines instead of eighty. The trade is that inference is a heuristic and
occasionally wrong (see the two warnings above). At Google's scale Bazel wins; at this one it does
not.
vs **Make plus per-language tools**: what we had. It works until CI needs a hand-edit per new
service, which is precisely what [[paved-paths]] was supposed to eliminate.

## Official docs

- Site: https://www.pantsbuild.org/
- Backends: https://www.pantsbuild.org/stable/docs/using-pants/key-concepts/backends
- Source roots: https://www.pantsbuild.org/stable/docs/using-pants/key-concepts/source-roots
- Dependency inference: https://www.pantsbuild.org/stable/docs/using-pants/key-concepts/targets-and-build-files
- PEX and `complete_platforms`: https://www.pantsbuild.org/stable/docs/python/overview/pex
- Python lockfiles: https://www.pantsbuild.org/stable/docs/python/overview/lockfiles

> [!tip] Related
> [[pex]], [[grpc]], [[vite]], [[uv]], [[go]], [[fastapi]], [[buildah]], [[buildkite]], [[sonatype-nexus]], [[supply-chain-choke-point]]

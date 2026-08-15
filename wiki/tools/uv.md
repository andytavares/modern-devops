---
type: tool
tags: [python, packaging, build]
role: Python dependency resolution and locking
version: 0.12.x
docs: https://docs.astral.sh/uv/
date_added: 2026-08-15
date_updated: 2026-08-15
status: in-use
---

# uv

> [!info] One-liner
> A Rust-based Python package manager that resolves and installs an order of magnitude faster than pip, and writes a real lockfile.

## What it does here

Manages `services/order-api` dependencies and produces `uv.lock`, which is committed. In the
Dockerfile, `uv sync --no-install-project` installs dependencies as their own layer so it caches
across code changes (§3.1). In CI, `uv sync --locked` fails if the lockfile is out of date rather
than silently resolving something new.

Points at [[sonatype-nexus]]'s PyPI proxy through `UV_INDEX_URL` / `UV_INSECURE_HOST` (§12.5), so
builds never reach pypi.org directly.

## Key concepts

- **`--locked` in CI is the important flag.** It turns "the lockfile drifted" from a silent behaviour
  change into a failed build.
- **Layer ordering is a caching decision**: dependencies before source, always.
- `uv run` executes inside the project environment without an explicit activate step.

## Pinning the interpreter — two mechanisms, two jobs

| Mechanism | Scope | Job |
|---|---|---|
| `.python-version` (via `uv python pin 3.13`) | this project's venv | selects *which interpreter* uv uses locally |
| `requires-python = ">=3.13,<3.14"` | packaging metadata | constrains *resolution*, so the lock can't target an interpreter the container won't run |

You need both. uv will download a missing interpreter automatically, so pinning costs nothing.

> [!warning] The failure this prevents is spectacularly misleading (hit 2026-08-15)
> With `requires-python = ">=3.13"` and no `.python-version`, uv picks the **newest** interpreter on
> the machine — Homebrew's `python3`, which was 3.14.7. `pydantic-core` 2.33.2 (from `pydantic`
> 2.11.7) publishes wheels for cp39–cp313 only, so uv fell back to a **source build**, which needs
> Rust and `maturin`, and died with:
>
> ```
> error: the configured Python interpreter version (3.14) is newer than
>        PyO3's maximum supported version (3.13)
> ```
>
> Nothing in that message mentions Python version pinning. The two obvious readings — "pydantic is
> broken" and "I need to install Rust" — are both wrong, and the suggested
> `PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1` is a trap: it "works" by compiling from source and leaves
> you testing on a different Python than the `python:3.13-slim` container ships.
>
> **Rule of thumb: a source build of a package that normally ships wheels means your interpreter is
> off the supported matrix.** Check the Python version before you debug the compiler.
>
> Verified facts, as of 2026-08: `pydantic-core` 2.33.2 wheel tags are cp39–cp313 + pp39–pp311;
> cp314 wheels first appear in `pydantic-core` **2.35.0** (i.e. a much newer `pydantic`). Upgrading
> pydantic is therefore *a* fix, but the wrong one here — it would put local on 3.14 while production
> stays on 3.13. Match the container instead.

## Dev/prod parity

The Dockerfile is `FROM python:3.13-slim`. An unpinned local interpreter means you test on one Python
and ship on another and find out at the worst possible time. **Pin the interpreter in the same commit
that pins the dependencies.**

## Official docs

- Docs: https://docs.astral.sh/uv/
- Locking and syncing: https://docs.astral.sh/uv/concepts/projects/sync/
- Index configuration: https://docs.astral.sh/uv/configuration/indexes/
- Python version management / pinning: https://docs.astral.sh/uv/concepts/python-versions/
- PyO3 supported Python versions: https://pyo3.rs/

> [!tip] Related
> [[fastapi]], [[sonatype-nexus]], [[supply-chain-choke-point]]

---
type: tool
tags: [python, packaging, build]
role: Python dependency resolution and locking
version: 0.12.x
docs: https://docs.astral.sh/uv/
date_added: 2026-08-15
date_updated: 2026-08-16
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

Points at [[sonatype-nexus]]'s PyPI proxy through `[[tool.uv.index]]` in `pyproject.toml` (§3.1) — not
through a CI environment variable — so builds never reach pypi.org directly. See below for why the
distinction is load-bearing.

## The index must be declared in the project, not in CI

`uv.lock` records the **registry each package came from**. uv then refuses a lockfile whose
registries aren't in the current index configuration. From uv's own resolver
(`crates/uv/src/commands/project/lock.rs`):

> *"If the user provided at least one index URL (from the command line, or from a configuration
> file), don't use the existing lockfile if it references any registries that are no longer included
> in the current configuration."*

So the tempting split — `pyproject.toml` pointing at PyPI, `UV_DEFAULT_INDEX` set only in the
pipeline — **cannot work**. A lock generated on a laptop against `pypi.org` can never satisfy a build
pointed at Nexus.

```toml
[[tool.uv.index]]
url = "http://nexus:8081/repository/pypi-proxy/simple"
default = true

[tool.uv]
allow-insecure-host = ["nexus"]   # plain HTTP, §5.8; moved here from [tool.uv.pip] in uv 0.5.x
```

With this, CI needs **no** uv-specific environment at all — verified by running the full step in
`python:3.13-slim` with only `PIP_*` set (pip still needs an index to install uv itself).

The cost: `nexus:8081` is pinned into the project and only resolves in this environment (§5.7). That
is the honest price of a hermetic index, and the same trade a real internal mirror makes.

> [!warning] The failure this prevents, hit 2026-08-15
> CI failed with **"The lockfile at `uv.lock` needs to be updated, but `--locked` was provided"** on a
> lockfile that had just been committed and that passed `uv lock --check` locally. Reproduced exactly
> by setting the CI index locally:
>
> ```
> $ uv lock --check                                       # against pypi.org
> Resolved 59 packages
> $ UV_INDEX_URL=http://nexus:8081/... uv lock --check     # against nexus
> error: The lockfile at `uv.lock` needs to be updated
> ```
>
> The `hint: run uv lock` is actively misleading — running it against the wrong index just moves the
> failure to the other environment.

> [!note] `UV_INDEX_URL` is deprecated
> Superseded by `UV_DEFAULT_INDEX` (uv 0.4.23+). Both still work. The tutorial dropped them from the
> pipeline entirely rather than renaming, since `pyproject.toml` now carries the index.

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

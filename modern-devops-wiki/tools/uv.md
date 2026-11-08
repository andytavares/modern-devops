---
type: tool
tags: [python, dependencies, superseded]
role: Python dependency resolution and locking — superseded by Pants for building
version: 0.12.x
docs: https://docs.astral.sh/uv/
date_added: 2026-08-17
date_updated: 2026-08-17
status: superseded
---

# uv

> [!info] One-liner
> How order-api resolved and locked its dependencies in §3.1, before [[pants]] took the job in §17. Its lockfile-and-index lesson is the reason the page is still here.

## Status: superseded, deliberately

§19.7 removes both files:

```bash
git rm services/order-api/pyproject.toml services/order-api/uv.lock
```

Dependencies now resolve from `locks/python-default.lock` via Pants, so the uv pair described a build
nobody runs — **and a stale lockfile is worse than none, because the next person to read it will
believe it.**

§17.1 is equally clear about the other direction: **with one service in one language, Pants is pure
overhead and uv is the better answer.** This is not "uv was wrong"; it is "the thing that justified
replacing it did not exist until Phase 5 made adding services cheap."

## The lesson that outlives the tool

> [!warning] Declaring the index only in CI can never work
> It is tempting to leave `pyproject.toml` pointing at PyPI and set `UV_DEFAULT_INDEX` in the pipeline.
> That combination **cannot** work, and the failure is delayed until CI. From uv's own resolver:
> *"If the user provided at least one index URL … don't use the existing lockfile if it references any
> registries that are no longer included in the current configuration."*
>
> So a lock generated against `pypi.org` can never satisfy a build pointed at
> [[sonatype-nexus]], and `uv sync --locked` fails with **"The lockfile at `uv.lock` needs to be
> updated"** — on a lockfile you just committed and which passes locally.

The fix is to declare the index in the project so it lands *in the lock*:

```toml
[[tool.uv.index]]
url = "http://nexus:8081/repository/pypi-proxy/simple"
default = true

[tool.uv]
allow-insecure-host = ["nexus"]   # §5.8 runs Nexus on plain HTTP
```

**This generalises past uv.** [[pants]] does the same thing in `pants.toml` (`[python-repos] indexes`),
and `.buildkite/pipeline.sh` still sets `PIP_INDEX_URL` only for the one thing that predates the lock —
installing tooling itself. The honest cost is that it pins `nexus:8081` into the project, resolvable
only in this environment. That is the same trade a real internal PyPI mirror makes.

## Pin the interpreter in the same commit that pins the dependencies

> [!warning] Skipping `uv python pin` produces a spectacular, misleading failure
> Without it, uv picks the newest interpreter satisfying `requires-python`. If that is newer than the
> newest CPython `pydantic-core` publishes wheels for, uv **builds it from source**, and you get a wall
> of Rust output ending in `the configured Python interpreter version (3.14) is newer than PyO3's
> maximum supported version (3.13)`. Nothing in that message mentions Python pinning, and the obvious
> readings — "pydantic is broken", "I need Rust" — are both wrong.

Two mechanisms doing different jobs: `.python-version` selects the interpreter for *this project's
venv*; `requires-python = ">=3.13,<3.14"` is packaging metadata constraining *resolution*, so the
lockfile can never resolve against an interpreter the container will not run. The deeper point is
dev/prod parity — an unpinned local interpreter means you test on one Python and ship on another.

Pants states the same constraint as `[python] interpreter_constraints = [">=3.13,<3.14"]`.

## Related

[[pants]] · [[sonatype-nexus]] · [[fastapi]] · [[supply-chain-choke-point]] · [[pydantic]]

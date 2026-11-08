---
type: concept
tags: [build-system, monorepo]
date_added: 2026-08-17
date_updated: 2026-08-17
---

# Dependency inference, and where to stop trusting it

> [!info] One-liner
> [[pants]] reads your source and builds the dependency graph from imports. That is why the `BUILD` files here are eight lines rather than eighty — and it is also a heuristic, with one failure mode that produces a green build and a broken artifact.

## What inference buys

Bazel is a build system you write build files *for*, in a language of its own, for every target — for a
Python service that means `rules_python`, a `pip_parse` repository rule, and a `py_binary` per entry
point, all by hand.

Pants resolves `from shop.v1 import pricing_pb2` to the target that generates it, without being told.
Concretely: **nothing was added to `services/order-api/BUILD` when order-api started calling
[[grpc]].** Confirm rather than assume:

```bash
pants dependencies --transitive services/order-api:bin | grep protos
# protos/shop/v1/pricing.proto:protos
```

`pants dependencies` is the tool for "this behaves as if a file is missing" — it prints the graph Pants
**actually built**, rather than the one you assumed from reading imports.

It also means one requirements file does not mean one fat artifact: `3rdparty/python/requirements.txt`
resolves once into `locks/python-default.lock`, and each target still ships only what it imports.

## Where inference stops, and the rule that follows

> [!warning] Outside Python, enumerate the inputs by hand
> A build script's inputs are **not imports**. `tsconfig.json`, `vite.config.ts`, `index.html` and
> `src/style.css` are invisible to inference, so `frontend/BUILD` lists every one of them explicitly.
>
> **Omitting a config file fails loudly. Omitting an asset does not fail at all** — [[vite]] builds
> successfully in a sandbox that simply does not contain `style.css`, and emits a bundle with no
> styles. A broken page and a green build.

Same shape in Python where the thing is not code: `services/order-api/BUILD`'s `:openapi-spec` is a
`resource`, so nothing infers it, and the drift test reads it off disk by path — which is why
`python_tests` lists it in `dependencies` explicitly.

## The other place a heuristic needs help

Ambiguity. Two services shipping a top-level `app` package make `from app.settings import settings`
genuinely undecidable, so Pants cannot infer intra-service imports and [[mypy]] refuses to run at all.
The [[backstage]] skeleton's `BUILD` also declares `dependencies=[":lib"]` on its tests explicitly,
with the comment *"several services could otherwise satisfy this import."* See [[pants]].

## Target *type* is part of the declaration

`typescript_sources()` with no arguments sweeps up `tally.test.ts` — a file Pants then owns and never
runs. `typescript_tests` is what makes `pants test ::` run it. `pants tailor --check` fails on a source
file with no target **or the wrong one**, which is what catches this.

## The general lesson

Inference is a strong default and a weak guarantee. **Trust it where the language's import graph is the
real dependency graph; enumerate everywhere else** — and prefer the failure that is loud. Where a
silent omission is possible, a check has to exist: that is the same argument as
[[order-platform]]'s `verify_chart.py`.

## Related

[[pants]] · [[vite]] · [[grpc]] · [[mypy]] · [[order-platform]] · [[backstage]]

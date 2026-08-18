---
type: tool
tags: [frontend, build-system]
role: the Canary Watch dashboard that makes a traffic shift visible in a browser
version: vite 8.2.1, typescript 7.0.2, Node ≥22.12
docs: https://vite.dev/guide/
date_added: 2026-08-17
date_updated: 2026-08-17
status: in-use
---

# Vite

> [!info] One-liner
> Builds `frontend/` — a TypeScript page with no framework that POSTs orders, tallies `priced_by` on each response, and draws a bar. A 90/10 → 50/50 [[istio]] weight change is visible in seconds.

## Why a dashboard earns its place

It is a demo, and it justifies itself for one reason: **it makes the canary a thing you watch rather
than a thing you query.** The same information is in [[prometheus]]. Nobody stands at a Prometheus
console watching a ratio move (§19.4).

The mechanism is `served_by` off the [[grpc]] wire, renamed once to `priced_by` on the way out of
order-api, never aggregated in between.

## Under Pants

`frontend/BUILD` uses `package_json` with a `node_build_script` on the `build` entry point, output
directory `dist`. `frontend/src/BUILD` uses `typescript_sources()` plus a separate
`typescript_tests()` target.

**`typescript_sources()` with no arguments takes the directory's `.ts` files — including the test
file, which is then a file Pants owns and never runs.** `typescript_tests` is what makes
`pants test ::` run `tally.test.ts`, and it is what `pants tailor --check` demands: tailor fails on a
source file with no target, *or the wrong one*. `style.css` is a `resource`, not a source, because
nothing imports it in a way inference can follow.

> [!warning] Every dependency in `frontend/BUILD` is listed by hand, and that is the rule outside Python
> [[pants]] infers dependencies from **imports**, and a build script's inputs are not imports:
> `tsconfig.json`, `vite.config.ts`, `index.html` and `src/style.css` are invisible to inference.
> Omitting a config file fails loudly. **Omitting an asset does not fail at all** — Vite builds
> successfully in a sandbox that simply does not contain `style.css` and emits a bundle with no styles,
> which is a broken page and a green build. Enumerate the inputs. See [[dependency-inference]].

## The one deliberate inconsistency

The frontend's Dockerfile runs the Vite build itself in a `node` stage rather than copying a Pants
artifact, unlike the other three services. The reason: **a static bundle is platform-independent** — it
has none of the problem [[cross-compilation]] and [[pex]]'s `complete_platforms` exist to solve — so the
artifact handoff buys nothing. Worth revisiting if the node stage gets slow.

It is recorded rather than smoothed over, because **an unexplained inconsistency is how the next person
concludes the pattern does not matter** (§19.4).

## Two edge facts

It gets **`app.localtest.me`**, not `shop.localtest.me` — order-api already owns that host and
[[ingress-nginx]]'s admission webhook rejects a duplicate host/path outright.

And `frontend/nginx.conf` must proxy to the **Service** port (`80`), not the container port (`8000`).
Point it at 8000 and every order in the dashboard reads `HTTP 502` while a direct `curl` at order-api
returns `202`, sending you to look at the wrong service entirely. `checks/verify_chart.py` asserts the
two agree — see [[order-platform]].

## Related

[[pants]] · [[grpc]] · [[istio]] · [[order-platform]] · [[ingress-nginx]] · [[dependency-inference]]

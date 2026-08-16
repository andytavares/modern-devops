---
type: tool
tags: [frontend, typescript, build]
role: Builds the Canary Watch dashboard — the frontend that makes a traffic shift visible
version: vite 8.2.1, typescript 7.0.2 (frontend/package.json)
docs: https://vite.dev/
date_added: 2026-08-16
date_updated: 2026-08-16
status: in-use
---

# Vite

> [!info] One-liner
> A frontend build tool that turns TypeScript and an HTML entry point into a static bundle nginx can serve — no framework, no runtime.

## What it is

A dev server and bundler. `vite build` emits static assets to `dist/`; there is no server-side
component and nothing of Vite ships to the browser. Configuration is a `vite.config.ts` that is
usually a few lines.

## What it does here

`frontend/` is the **Canary Watch** dashboard (§19.4): TypeScript, no framework, ~250 lines. It polls
`order-api`, tallies which pricing version served each order via the response's `served_by` field, and
draws a live bar. A 90/10 → 50/50 [[istio]] weight change is visible in a browser within seconds.

The build is `tsc --noEmit && vite build` — typecheck and bundle as separate concerns, so a type error
fails the build rather than being erased by the transpiler.

It earns its place for one reason: **it makes the canary something you watch rather than something you
query.** The same information is in [[prometheus]]. Nobody stands at a Prometheus console watching a
ratio move.

The image is a multi-stage build ending in `nginxinc/nginx-unprivileged`, which runs as a non-root
user on port 8080 out of the box — matching the `runAsNonRoot` security context every other workload
here runs under.

## Under Pants: inference does not reach a build script's inputs

`frontend/BUILD` declares a `package_json` with a `node_build_script`, plus the frontend's own
`typescript_sources()`. Both Pants backends involved (`experimental.javascript`,
`experimental.typescript`) are experimental — see [[pants]].

> [!warning] A missing asset produced no error at all — hit 2026-08-16
> Pants infers dependencies from **imports**, and a build script's inputs are not imports.
> `tsconfig.json`, `vite.config.ts`, `index.html` and `src/style.css` are invisible to inference and
> must be declared by hand:
>
> ```python
> file(name="tsconfig", source="tsconfig.json")
> resource(name="style_css", source="style.css")
> ```
>
> The missing `style.css` is the instructive case. Vite did **not** fail — it built successfully in a
> sandbox that simply did not contain the file, and emitted a bundle with no styles. The result was a
> broken page and a green build. A missing `tsconfig.json` at least fails loudly; a missing asset does
> not fail at all.
>
> **Rule: for any non-Python target, enumerate the build's inputs explicitly and do not trust
> inference.** It is a Python-first feature the experimental backends inherit unevenly.

## The deliberate inconsistency

Unlike the three services, the frontend's Dockerfile runs the Vite build itself in a `node` stage
rather than copying a [[pex]]-style prebuilt artifact from `dist/`. A static bundle is
platform-independent, so it has none of the cross-compilation problem `complete_platforms` exists to
solve, and the artifact handoff would buy nothing.

This is recorded rather than smoothed over. An unexplained inconsistency is how the next person
concludes the pattern does not matter. Worth revisiting if the node stage gets slow.

## The tally bug worth remembering

The first implementation was:

```ts
if (priced_by === "v1") v1++; else v2++;
```

which counts every unexpected value as `v2`. A dashboard whose entire job is showing a ratio would
have shown a confident, wrong split — and `served_by` is a free-form string on the wire, not a closed
union (see [[grpc]]). It now keys on the actual string with a per-key bar segment and a stable colour,
and a regression test asserts an unknown value does not inflate a bucket that was never seen.

**The general rule: an `else` branch is a fallback bucket, and a fallback bucket in a ratio display is
a lie with a default value.**

## Key concepts

- **Resolves npm through [[sonatype-nexus]]** via `frontend/.npmrc`, and `npm ci` against a committed
  `package-lock.json` — the same [[supply-chain-choke-point]] discipline as [[uv]] and Go modules.
- **Its own Ingress host, `app.localtest.me`**, deliberately not `shop.localtest.me`: `order-api`
  already owns that host and [[ingress-nginx]]'s admission webhook rejects a duplicate outright.
- **`nginx-unprivileged` needs writable `/tmp`, `/var/cache/nginx` and `/var/run`** to run under
  `readOnlyRootFilesystem`. Like the [[pex]] failure, it renders and dry-runs perfectly and
  crash-loops only at runtime.
- **Tests run under `node --test`**, not a browser — the tally logic is kept DOM-free in its own
  module precisely so it can be unit tested.

## Why this, not the alternative

vs **React/Next.js**: this page has one number and one bar. A framework would be more code, a larger
image, and a second thing to keep patched, for no capability we use.
vs **a Grafana panel**: honestly a reasonable answer, and [[grafana]] already has the data. A separate
page exists because the point is to demonstrate that *your own application* can observe the mesh's
behaviour, not just your monitoring stack.
vs **plain `tsc` and a `<script>` tag**: viable at this size. Vite gives dev-server reload and a
bundler for roughly zero config, and is what a real frontend would use.

## Official docs

- Site: https://vite.dev/
- Build options: https://vite.dev/config/build-options.html
- Static deploy: https://vite.dev/guide/static-deploy.html
- nginx-unprivileged: https://github.com/nginxinc/docker-nginx-unprivileged

> [!tip] Related
> [[pants]], [[grpc]], [[istio]], [[ingress-nginx]], [[sonatype-nexus]], [[order-platform]], [[prometheus]]

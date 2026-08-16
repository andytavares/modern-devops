# Phase 7 — One build system, many languages

[← All phases](README.md) · [← Phase 5 — Making it someone else's platform](phase-5-developer-portal.md) · [Phase 6 — Operating it, and taking it down →](phase-6-operating.md)

> **Where this starts:** two services, two toolchains, two CI steps, and no shared contract between them.
> **Where it ends:** one command that lints, typechecks, tests and packages Python, Go and TypeScript, and one `.proto` that both Python and Go compile against.

Phase 5 made adding a service cheap. That is the problem this phase exists to solve.

Every service so far carries its own build: `order-api` has a `pyproject.toml` and a `uv.lock`,
`order-worker` has a `go.mod`, and [§12.5](phase-3-delivery.md#125-the-pipeline) has one CI step per
language to drive them. That is fine at two services. At five it is a pipeline that must be edited, in
a language-specific way, every time someone uses the paved path — which is precisely the manual step
Phase 5 claimed to have removed.

There is a second, worse problem, and it is the one that actually justifies the work. `order-api` and
`order-worker` share a data model and share it *by convention*: a JSON shape agreed in a code review
and re-declared in two languages. Nothing catches it when one side changes. The failure lands at
runtime, in a cluster, as a decode error on a message that was already committed to Kafka.

This phase replaces both with a monorepo build system ([[pants]]) and a real interface definition. The
test of whether it worked: **change a field in a `.proto` and watch two languages fail in the same
command, on your laptop, before anything reaches a cluster.**

> **This phase is numbered 7 and sits before Phase 6.** The number records when it was built —
> after the platform was already running — and the position records where it belongs when reading.
> Phase 6 ends by deleting the cluster; nothing sensibly comes after that. See
> [Why this order](README.md#why-this-order).

---

## 17. Pants: one build system for four languages

### 17.1 The problem with a build tool per language

The honest case against doing this at all, first. A monorepo build system is a large, opinionated
dependency that every developer must install and every CI job must bootstrap. If you have one service
in one language, it is pure overhead and `uv` is a better answer. **Do not adopt this because it is
sophisticated.** Adopt it when you can name the specific thing it fixes.

Here there are three, and they are all consequences of earlier phases:

| Problem | Created by | What Pants does about it |
|---|---|---|
| One CI step per language, hand-edited per service | [§12.5](phase-3-delivery.md#125-the-pipeline) | One `pants lint check test ::` that discovers targets |
| No shared contract between `order-api` and `order-worker` | [§3](phase-1-the-application.md#3-the-applications) | One `.proto` generating both languages, checked together |
| Image builds that resolve dependencies inside a privileged Buildah pod | [§12.5](phase-3-delivery.md#125-the-pipeline) | Artifacts built once upstream; the image is `FROM` plus `COPY` |

The third is a security argument, not an ergonomics one. A Buildah pod runs `privileged: true`
([§12.5](phase-3-delivery.md#125-the-pipeline)); the less that pod does, the better. Today it resolves
a dependency tree from a network index. After this phase it copies a file.

> **Why Pants and not Bazel.** Bazel is the better-known answer and the more powerful one. It is also
> a build system you write build files for, in a language of its own, for every target — and for a
> Python service that means `rules_python`, a `pip_parse` repository rule, and a `py_binary` per
> entry point, all written by hand. Pants infers dependencies from **imports**: it reads the source,
> resolves `from shop.v1 import pricing_pb2` to the target that generates it, and builds the graph
> without being told. That is why the `BUILD` files in this repo are eight lines rather than eighty.
> The cost is that inference is a heuristic and occasionally wrong, which is what
> [§17.4](#174-source-roots-and-the-duplicate-module-trap) is about. For a small polyglot repo the
> trade is clearly worth it; at Google's scale it clearly is not.

### 17.2 Backend maturity, stated up front rather than discovered later

Pants ships language support as backends. Not all of them are stable, and you should know which
before you build a platform on them:

| Backend | Status | Used for |
|---|---|---|
| `pants.backend.python` | stable | `order-api`, `pricing` |
| `pants.backend.python.typecheck.mypy` | stable | typechecking |
| `pants.backend.codegen.protobuf.python` | stable | Python gRPC stubs |
| `pants.backend.experimental.python.lint.ruff.check` / `.format` | **experimental** | linting and formatting |
| `pants.backend.experimental.go` | **experimental** | `order-worker` |
| `pants.backend.experimental.codegen.protobuf.go` | **experimental** | Go gRPC stubs |
| `pants.backend.experimental.javascript` | **experimental** | the frontend's npm install |
| `pants.backend.experimental.typescript` | **experimental** | the frontend's sources |

Five of the eight are experimental, as of Pants 2.33.0 / 2026-08. That is a real risk and it is taken
knowingly: the entire value of a polyglot monorepo is that one tool builds everything, so refusing the
experimental backends means not doing this at all. The mitigation is that **every one of them has a
one-command escape hatch** — `go build`, `npm run build`, `ruff check` — because Pants delegates to
the language's own toolchain rather than reimplementing it. If a backend breaks on upgrade, you lose
orchestration, not the ability to ship.

> [!warning] **In 2.33 the ruff backend path is not where the docs' muscle memory puts it, and the wrong path fails as a `ModuleNotFoundError`.**
> It is `pants.backend.experimental.python.lint.ruff.check` and
> `pants.backend.experimental.python.lint.ruff.format`, **not** `pants.backend.python.lint.ruff.*`.
> The trap is that the non-experimental path is not simply absent: it exists on disk as a directory
> containing `rules.py` but **no `register.py`**. So Pants does not say "unknown backend" — it tries
> to import a module that is not a backend and dies with:
>
> ```
> ModuleNotFoundError: No module named 'pants.backend.python.lint.ruff.register'
> ```
>
> which reads like a broken Pants installation rather than a typo in your config.
>
> Related, same session: `[ruff]` takes **no** `install_from_resolve`. Ruff ships as a downloaded
> binary, not a resolved Python package, so it is not in the lockfile and does not want to be. `mypy`
> is the opposite — it *is* a resolved package and *does* take `install_from_resolve`. Two linters,
> two mechanisms, one config file.

### 17.3 `pants.toml`

Install Pants the same way CI will — from PyPI **through Nexus**, so the build system crosses the same
supply-chain choke point as everything it builds ([§5.1](phase-0-foundations.md#51-what-nexus-is-actually-for)):

```bash
pip install "pantsbuild.pants==2.33.0"
```

> **Not `curl … | bash`.** Pants' documented install is a shell launcher fetched from the internet.
> That is a build system entering your supply chain through a door you spent [§5](phase-0-foundations.md#5-sonatype-nexus-the-artifact-choke-point)
> closing. Installing the wheel from Nexus costs nothing and keeps the rule intact: **nothing enters
> this platform except through the choke point**, including the thing that builds it.

The configuration is short, and every non-obvious line is there because something failed without it:

```toml
[GLOBAL]
pants_version = "2.33.0"

backend_packages = [
  "pants.backend.python",
  "pants.backend.experimental.python.lint.ruff.check",
  "pants.backend.experimental.python.lint.ruff.format",
  "pants.backend.python.typecheck.mypy",
  "pants.backend.codegen.protobuf.python",
  "pants.backend.experimental.go",
  "pants.backend.experimental.codegen.protobuf.go",
  "pants.backend.experimental.javascript",
  "pants.backend.experimental.typescript",
]

pants_ignore.add = ["/portal", "/wiki", "/raw", "/docs"]

[source]
root_patterns = ["/", "/services/*", "/protos"]

[python]
interpreter_constraints = [">=3.13,<3.14"]
enable_resolves = true
default_resolve = "python-default"

[python.resolves]
python-default = "locks/python-default.lock"

[python-repos]
indexes = ["http://nexus:8081/repository/pypi-proxy/simple"]

[golang]
subprocess_env_vars = [
  "GOPROXY=http://nexus:8081/repository/go-proxy",
  "GOSUMDB=off",
  "GOFLAGS=-mod=mod",
  "HOME",
  "PATH",
]

[python-protobuf]
generate_type_stubs = true
```

Four of those deserve a sentence:

- **`pants_ignore` excludes `/portal`.** Backstage owns a Yarn workspace with its own build; putting
  it under Pants' JS backend means two tools fighting over one `node_modules`. It is not ours to build
  ([§14.8](phase-5-developer-portal.md#148-build-and-deploy-the-portal)).
- **`[python-repos]` and `[golang]` both point at Nexus**, for the same reason `uv` did
  ([§5.1](phase-0-foundations.md#51-what-nexus-is-actually-for)). `GOSUMDB=off`
  because the public checksum database is unreachable through a private proxy — the same trade, and
  the same caveat, as [§12.5](phase-3-delivery.md#125-the-pipeline).
- **`enable_resolves` with a single named lockfile** means every Python target in the repo resolves
  against `locks/python-default.lock`. One lock, one resolution, no chance of two services
  disagreeing about `protobuf`. Pants still computes per-target dependencies from imports, so a
  service ships only what it imports — one requirements file does not mean one fat artifact.
- **`generate_type_stubs`** is [§18.3](#183-why-protoc-must-emit-pyi-stubs).

Generate the lockfile and commit it:

```bash
pants generate-lockfiles --resolve=python-default
git add locks/python-default.lock 3rdparty/python
```

> [!warning] **`brew install python@3.13` puts the interpreter somewhere Pants cannot see.**
> Pants reported:
>
> ```
> No working interpreter compatible with the requested constraints was found
> ```
>
> with a perfectly good CPython 3.13 installed. Homebrew puts the unversioned `python` in
> `libexec/bin`, which is deliberately **not** on `PATH` — so `python3.13` exists and Pants' search
> still finds nothing. The fix is to tell it where to look:
>
> ```toml
> [python-bootstrap]
> search_path = ["<PYENV>", "<PATH>", "/opt/homebrew/opt/python@3.13/libexec/bin"]
> ```
>
> `<PYENV>` and `<PATH>` are the defaults and must be repeated, not replaced. The message names the
> constraint, which sends you to `interpreter_constraints` — the wrong file entirely.

### 17.4 Source roots, and the duplicate-module trap

`root_patterns = ["/", "/services/*", "/protos"]` declares the import roots. `/services/*` means
each service directory is its own root, so `services/order-api/order_api/main.py` is importable as
`order_api.main`. `/protos` means generated code is importable as `shop.v1.pricing_pb2` rather than by
a path that leaks the directory layout.

That second root is worth doing deliberately. Without it, both services would import their shared
contract by a path — and a path is a thing that changes when someone reorganises a directory.

> [!warning] **Every service with a top-level `app` package collides, and mypy refuses outright.**
> `order-api` shipped its code in `app/` — the FastAPI convention, and what
> [§3.1](phase-1-the-application.md#31-order-api-python--fastapi) wrote. When `pricing` arrived with its own
> `app/`, both sat under the shared `/services/*` source root as the module `app`, and:
>
> ```
> Duplicate module named "app"
> ```
>
> mypy does not degrade here; it declines to run at all. Pants also cannot infer intra-service
> imports, because `from app.settings import settings` is genuinely ambiguous — there are two.
>
> The fix is a rename, not a config flag: `app/` → `order_api/` and `app/` → `pricing/`. Once a
> package name is unique across the repo, inference works and mypy is happy.
>
> **This is a property of the source-root layout, not of these two services.** Any repo that gives
> each service its own source root must also give each service a unique top-level package name. The
> FastAPI tutorial convention — every project has an `app` — is exactly wrong at more than one
> project.

> [!warning] **The paved path was a machine for producing that failure, and it is only half fixed.**
> The Backstage skeleton ([§14.6](phase-5-developer-portal.md#146-paved-path-1--a-new-service))
> emitted `app/` too, so the *first* scaffolded service would work and the *second* would break
> `pants check` for the whole repo — including for people who had never used the portal. The skeleton
> now templates its package directory as `${{ values.name | replace("-", "_") }}`, the same way its
> metric prefix already was, because service names are hyphenated and Python packages may not be.
> Verified by rendering it as `quotes-api` and running its tests.
>
> **Still open:** the skeleton emits `pyproject.toml` and `uv.lock`, not a `BUILD` file. A scaffolded
> service therefore arrives *outside* the monorepo this phase just built — and since
> [§19.5](#195-one-ci-step-instead-of-two) makes CI discover services by the presence of `BUILD`, a
> scaffolded service is currently not built at all by the pipeline. Making the paved path emit a
> `BUILD` file is the obvious next commit and deliberately is not this one. Tracked in
> [`wiki/open-questions.md`](../wiki/open-questions.md).

### 17.5 One command, and what it actually does

```bash
pants lint check test ::
```

`::` means "every target in the repo". One invocation runs ruff over Python, `go vet` over Go, mypy
over both Python services *including the generated protobuf stubs*, and every test suite in the repo.
Adding a fourth language is a line in `backend_packages`, not a new CI step.

```bash
pants list ::                    # every target Pants knows about
pants dependencies --transitive services/order-api:bin
pants package services/pricing:bin
```

`pants dependencies` is the one to reach for when something behaves as if a file is missing: it prints
the graph Pants actually built, which is the graph that matters, rather than the one you assumed from
reading imports.

---

## 18. One `.proto`, two languages

### 18.1 The contract

**`protos/shop/v1/pricing.proto`** (comments stripped — the file itself carries the reasoning inline)

```protobuf
syntax = "proto3";

package shop.v1;

option go_package = "github.com/andytavares/modern-devops/protos/shop/v1;shopv1";

service Pricing {
  rpc PriceOrder(PriceOrderRequest) returns (PriceOrderResponse);
}

message PriceOrderRequest {
  string sku = 1;
  int32 quantity = 2;
  int32 unit_amount_cents = 3;
  string customer = 4;
}

message PriceOrderResponse {
  int32 total_amount_cents = 1;
  int32 discount_cents = 2;
  string rule_applied = 3;
  string served_by = 4;
}
```

`served_by` is the field the rest of this platform is built around: the pricing implementation writes
its own version into it, `order-api` passes it through, and the frontend
([§19.4](#194-the-frontend-vite-and-a-live-tally)) tallies it. That is what makes an Istio weight
change something you watch in a browser rather than infer from a metric.

Money is `int32` cents throughout. Floating-point currency is a bug you ship once.

**`protos/shop/v1/BUILD`** (comments stripped)

```python
protobuf_sources(
    name="protos",
    sources=["*.proto"],
    grpc=True,
)
```

`grpc=True` is not optional decoration — without it protoc emits message classes only, and the
`Pricing` service stub you actually need never appears. **One target feeds both language backends.**

### 18.2 Generate, and look at what came out

```bash
pants export-codegen protos/shop/v1:protos
```

```
protos/shop/v1/pricing.pb.go          Go messages
protos/shop/v1/pricing_grpc.pb.go     Go service stubs
protos/shop/v1/pricing_pb2.py         Python messages
protos/shop/v1/pricing_pb2_grpc.py    Python service stubs
```

You do not commit these and you do not usually run this command — `pants check`, `test` and `package`
generate into a sandbox on demand. `export-codegen` exists so you can *read* the output, and reading
it once is worth the minute.

Now the demonstration that justifies the whole phase. Rename `quantity` to `qty` in the `.proto` and
run:

```bash
pants check ::
```

Python fails on the attribute and Go fails to compile, in the same command, in about ten seconds. The
previous arrangement — a JSON shape agreed in review — surfaced the same mistake as a decode error in
a consumer, after the message was already durable in Kafka.

> **This is the entire argument for a monorepo**, and it is worth being precise about what the
> argument is *not*. It is not "one repo is tidier". It is that a shared interface can be **checked by
> a compiler across language boundaries**, and that check is only possible when one build system sees
> both sides. Split the repo and you are back to versioned artifacts, publish ordering, and a window
> during which the two sides disagree.

### 18.3 Why protoc must emit `.pyi` stubs

```toml
[python-protobuf]
generate_type_stubs = true
```

Generated Python protobuf modules do not define their message classes in the way a reader expects.
`pricing_pb2.py` calls `_builder.BuildTopDescriptorsAndMessages(...)` and the classes appear in
`globals()` **at import time**. mypy reads the file statically, finds no `class PriceOrderRequest`,
and reports:

```
"PriceOrderRequest" is not defined
```

mypy is correct. The class genuinely does not exist statically. `generate_type_stubs = true` has
protoc emit a `.pyi` next to each `_pb2.py` describing what will exist at runtime, and the error
disappears. Pants' own help prefers this to the older mypy-plugin option.

One more, in the same family: `grpcio` ships **no `py.typed` marker**, so mypy cannot see its types at
all regardless of stubs. `types-grpcio` in `3rdparty/python/requirements.txt` is the fix, and mypy's
own suggestion to install it is right. Verified by checking `pants export --resolve=python-default`
for a `py.typed` under `grpc/` — there isn't one.

---

## 19. A third service, PEX packaging, and a dashboard

### 19.1 `pricing`, deliberately synchronous

`services/pricing` serves `shop.v1.Pricing/PriceOrder` on port 50051, plus a small stdlib HTTP server
on 9090 for `/healthz`, `/readyz` and `/metrics` — Kubernetes probes and Prometheus both want HTTP,
and gRPC health checking is a bigger dependency than this needs.

Its behaviour is switched by `PRICING_VERSION` and echoed back in `served_by`:

- **v1** — list price. `total = unit_amount_cents × quantity`, no discount.
- **v2** — the same, except a line with `quantity >= 3` gets 10% off, integer math, rounded down.

That difference is chosen so an Istio weight change is *observable*. Two versions that behave
identically make a canary a matter of faith.

`order-api` calls it on the order path with a **2 second deadline**, using `grpc.aio` so a slow
pricing service cannot block the event loop. On timeout or `UNAVAILABLE` it returns **HTTP 502** and
increments `pricing_calls_total{result,served_by}`.

> **It does not fall back to a locally computed price, and that is a deliberate choice you should
> argue with.** A fallback is the kinder production design: the customer gets an order instead of an
> error. It is also the thing that would make every experiment in
> [§9.8](phase-4-service-mesh.md#98-canary-two-versions-of-pricing-behind-one-service) invisible — a
> canary you cannot see fail teaches nothing, and a silent fallback is how a dependency stays broken
> for a week. **The general rule: a fallback that is not itself alarmed on is a way of not finding
> out.** If you add one, add `pricing_calls_total{result="fallback"}` and an alert on it in the same
> commit.

Synchronous pricing also gives [Phase 4](phase-4-service-mesh.md) something it did not have. Until
now, `order-api` and `order-worker` were joined by Kafka and never called each other
([§9.1](phase-4-service-mesh.md#91-what-a-mesh-actually-buys-you-here--and-what-it-doesnt) is blunt
about the mesh having no request path to secure between them). `pricing` is the first synchronous
service-to-service hop in this platform, which is what makes retries, timeouts, traffic shifting and
outlier detection mean anything at all.

### 19.2 `pex_binary`, and the one flag that decides whether it runs

A PEX is a single executable zip containing your code and its entire dependency closure. `python
order-api.pex` runs it; there is no `pip install` step at any point after Pants.

**`services/pricing/BUILD`** (abridged):

```python
pex_binary(
    name="bin",
    entry_point="pricing/main.py:main",
    dependencies=[":lib"],
    complete_platforms=["3rdparty/python:linux-platform"],
    output_path="pricing.pex",
)
```

`output_path` exists so the artifact lands at `dist/pricing.pex` rather than the default
`dist/services.pricing/bin.pex`, which is what lets `dist/` be used directly as a Buildah build
context and the Dockerfile `COPY` by name.

> [!warning] **Without `complete_platforms`, the PEX builds clean, passes every check, and dies on import inside the container.**
> `pants package` on a macOS laptop resolves **macOS** wheels. `grpcio`, `pydantic-core`, `uvloop` and
> `watchfiles` are all native extensions, so the PEX you just built contains `.so` files for the wrong
> operating system and architecture entirely. Nothing local tells you: it builds, `pants test` passes,
> the image builds, the push succeeds. The failure is a Python `ImportError` at container start —
> maximum distance from the cause, in the one environment where you have the least visibility.
>
> The fix is to describe the target platform explicitly. Generate it from a real container rather than
> writing it by hand:
>
> ```bash
> docker run --rm python:3.13-slim sh -c \
>   'pip install pex && pex3 interpreter inspect --markers --tags' > 3rdparty/python/linux.json
> ```
>
> ```python
> file(name="linux-platform", source="linux.json")
> ```
>
> and reference it from **every** `pex_binary`. Verify by unzipping the result — you want
> `manylinux2014_aarch64` in the wheel filenames, not `macosx`:
>
> ```bash
> unzip -l dist/pricing.pex | grep -E 'manylinux|macosx' | head
> ```
>
> One constraint that follows and will eventually bite: when building for a platform other than the
> local one, **every platform-specific dependency must be available as a prebuilt wheel** for the
> target. Pants can only build sdists for the local machine. A dependency that ships source-only for
> `linux/aarch64` cannot be cross-packaged at all — you would have to build the wheel yourself and
> host it in [[sonatype-nexus]].
>
> **This is not a Pants quirk.** Any tool that resolves wheels on the build host and ships them to a
> different host has it — it is the same class of mistake as building a Go binary with `CGO_ENABLED=1`
> and putting it in `scratch`. The reason it bites *here* and did not bite before is that the old
> Dockerfile resolved dependencies **inside** a `linux/arm64` container, where the question could not
> arise.

The Dockerfile that consumes it is the whole payoff:

```dockerfile
FROM docker.io/library/python:3.13-slim

RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin appuser

WORKDIR /app
COPY --chown=10001:10001 pricing.pex /app/pricing.pex

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER 10001
EXPOSE 50051 9090
ENTRYPOINT ["python", "/app/pricing.pex"]
```

No `uv sync`, no layer-caching strategy, no index configuration, no build-time network access at all.
Compare it to [§3.1](phase-1-the-application.md#31-order-api-python--fastapi)'s multi-stage Dockerfile and the
argument makes itself.

### 19.3 A PEX needs somewhere to write, and `readOnlyRootFilesystem` gives it nowhere

This one was found by deploying it, not by reading it. `pricing` crash-looped with:

```
FileNotFoundError: [Errno 2] No usable temporary directory found in
['/tmp', '/var/tmp', '/usr/tmp', '/app']
```

> [!warning] **A PEX unpacks its dependency closure on first run, so `readOnlyRootFilesystem: true` breaks it — with no application log line at all.**
> The zip is not executed in place. On first run the PEX bootstrap extracts its wheels to `PEX_ROOT`
> — which Pex documents as defaulting to `~/.cache/pex` and which **must be writable** — falling back
> to the temp directory when it is not. Under `readOnlyRootFilesystem: true` every candidate fails, so
> it dies before importing a single line of your code, which means **none of your logging
> configuration has run** and nothing you wrote appears in `kubectl logs`. It reads exactly like a
> broken image rather than a pod spec that is one `emptyDir` short.
>
> The fix keeps the root filesystem read-only, which is the point:
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
> Set `PEX_ROOT` **explicitly** rather than relying on `/tmp` being writable — the default search
> order is an implementation detail, and an explicit path is a thing a reader can find.
>
> **Every service that moves to PEX packaging inherits this.** It is the same class of problem as
> `nginx-unprivileged` needing writable `/tmp`, `/var/cache/nginx` and `/var/run` — both render
> perfectly under `helm template`, pass `kubectl apply --dry-run=server`, and fail only at runtime.
> **Dry-run validates schema, not whether the process can start.**

Verified: `pricing-v1` and `pricing-v2` went from `CrashLoopBackOff` to `2/2 Running`, sidecars
included.

### 19.4 The frontend: Vite, and a live tally

`frontend/` is a [[vite]] + TypeScript page with no framework. It polls `order-api`, tallies which
pricing version served each order, and draws a bar. A 90/10 → 50/50 weight change is visible in a
browser within seconds.

It is a demo dashboard, and it earns its place for one reason: **it makes the canary a thing you watch
rather than a thing you query.** The same information is in Prometheus. Nobody stands at a Prometheus
console watching a ratio move.

**`frontend/BUILD`**

```python
package_json(
    scripts=[
        node_build_script(
            entry_point="build",
            output_directories=["dist"],
        ),
    ],
    dependencies=[
        ":npmrc",
        ":tsconfig",
        ":vite_config",
        ":index_html",
        "./src",
        "./src:style_css",
    ],
)

file(name="npmrc", source=".npmrc")
file(name="tsconfig", source="tsconfig.json")
file(name="vite_config", source="vite.config.ts")
file(name="index_html", source="index.html")
```

> [!warning] **Pants' JS/TS backend does not infer that a build script needs its config files or its non-TS assets, and a missing asset produces no error whatsoever.**
> Dependency inference works on **imports**, and a build script's inputs are not imports.
> `tsconfig.json`, `vite.config.ts`, `index.html` and `src/style.css` are all invisible to it, so they
> have to be listed by hand as `file` and `resource` targets.
>
> The missing `style.css` is the instructive one. Vite did not fail — it built successfully, in a
> sandbox that simply did not contain the file, and produced a bundle with no styles. The output was a
> **broken page and a green build**. A missing `tsconfig.json` at least fails loudly; a missing asset
> does not fail at all.
>
> **Rule: for any non-Python target, enumerate the build's inputs explicitly and do not trust
> inference.** Inference is a Python-first feature that the experimental backends inherit unevenly.

One deliberate inconsistency: the frontend's Dockerfile runs the Vite build itself in a `node` stage
rather than copying a Pants artifact, unlike the other three. The reason is that a static bundle is
platform-independent — it has none of the cross-compilation problem
[§19.2](#192-pex_binary-and-the-one-flag-that-decides-whether-it-runs) exists to solve — so the
artifact handoff buys nothing here. Worth revisiting if the node stage gets slow. It is recorded
rather than smoothed over because an unexplained inconsistency is how the next person concludes the
pattern does not matter.

The frontend gets its own Ingress on **`app.localtest.me`**, not `shop.localtest.me`. `order-api`
already owns that host ([§10.1](phase-1-the-application.md#101-one-chart-two-workloads)) and
ingress-nginx's admission webhook rejects a duplicate host/path outright.

### 19.5 One CI step instead of two

The Python step and the Go step are gone. In their place:

```yaml
  - label: ":hammer: lint · typecheck · test · package"
    key: verify
    artifact_paths: "dist/*"
    # ... python:3.13-slim pod ...
    command:
      - |
        pip install --quiet "pantsbuild.pants==2.33.0"
        git config --global --add safe.directory "$PWD"

        pants lint check test ::

        pants package \
          services/order-api:bin \
          services/order-worker:bin \
          services/pricing:bin

        ls -la dist/
```

Three things about this are load-bearing:

**`pants package` runs here, not in the image build.** The Buildah pods below it contain Buildah and
nothing else — no Python, no Go, no Node, no compiler. They `buildkite-agent artifact download` the
artifacts and copy them into an image. That is why every Dockerfile under `services/` is now four
lines, and why the build context is `dist/` rather than the source tree.

> [!warning] **The build context change breaks `COPY` in a way that reads as a missing file.**
> The context is `dist/`, so `COPY order-api.pex /app/` works and `COPY services/order-api/... `
> fails with "no such file or directory" — naming a path that exists perfectly well in the repo you
> are looking at. If you see that, check the context argument before you check the path.

**Service discovery now keys off `services/*/BUILD`**, not `Dockerfile`:

```sh
SERVICES="$(cd services && ls -d */ | sed 's#/##' | while read -r s; do
  [ -f "$s/BUILD" ] && [ -f "$s/Dockerfile" ] && echo "$s"
done | sort | tr '\n' ' ')"
```

A directory Pants does not know about cannot be built, tested or packaged — so it is not a service
this pipeline can deliver, and pretending otherwise produces a build step that fails at `COPY`. See
the open item in [§17.4](#174-source-roots-and-the-duplicate-module-trap): the Backstage skeleton does
not yet emit a `BUILD` file, so a scaffolded service does not currently satisfy this test.

**The `--build-arg VERSION` plumbing is gone entirely**, and it was never doing anything. See
[§19.6](#196-the-version-stamp-that-never-was).

### 19.6 The version stamp that never was

The old `order-worker` Dockerfile did this:

```dockerfile
ARG VERSION=dev
RUN CGO_ENABLED=0 GOOS=linux go build \
      -trimpath \
      -ldflags="-s -w -X main.version=${VERSION}" \
      -o /out/order-worker .
```

and CI passed `--build-arg VERSION=$SHA` into it.

> [!warning] **`-X main.version` was a silent no-op for the entire life of this tutorial.**
> `-ldflags "-X importpath.name=value"` sets a **string variable that already exists** in the compiled
> package. `main.go` has no `var version string` — it reads `SERVICE_VERSION` from the environment at
> startup, defaulting to `"dev"`:
>
> ```go
> version: getenv("SERVICE_VERSION", "dev"),
> ```
>
> When the symbol is absent, Go's linker does not error. It does not warn. It silently does nothing.
> So the `ARG`, the `--build-arg`, the per-service `BUILD_ARGS` special case in the pipeline, and the
> claim in [§3.2](phase-1-the-application.md#32-order-worker-go) that the SHA is stamped into the
> binary were all describing a mechanism that had never once run.
>
> The version a running `order-worker` actually reports comes from `SERVICE_VERSION`, set by the Helm
> chart from the image tag ([§10.1](phase-1-the-application.md#101-one-chart-two-workloads)).
>
> **The general lesson is about linker flags specifically: `-X` fails open.** Anything that
> misconfigures silently and produces a plausible artifact needs a test that asserts the *outcome*,
> not the flag. One `assert version != "dev"` in a smoke test would have caught this on day one.
>
> Pants' `go_binary` does support `linker_flags`, so this is reinstatable — but the honest fix was to
> delete the dead machinery, since `SERVICE_VERSION` from the chart already works and one mechanism
> beats two.

### 19.7 Commit

```bash
pants lint check test ::
pants package services/order-api:bin services/order-worker:bin services/pricing:bin
ls -la dist/

git add pants.toml 3rdparty locks protos services frontend .buildkite deploy
git commit -m "build: pants as the monorepo build system, one proto for two languages"
git push
```

`git push` builds all four images and Argo CD deploys them, exactly as
[Phase 3](phase-3-delivery.md) set up — the delivery path did not change, only what feeds it.

---

## Where you are

One command lints, typechecks, tests and packages three languages, and it needs no edit when a fourth
arrives. One `.proto` is compiled by both Python and Go, so a change to the contract fails on your
laptop rather than in a consumer at 3am. The images are `FROM` plus `COPY`, which means the privileged
Buildah pod no longer resolves anything from a network.

And there is now a synchronous call between two of your services — which is what
[§9.8](phase-4-service-mesh.md#98-canary-two-versions-of-pricing-behind-one-service) needs to shift
traffic between two versions of `pricing` and let you watch the split move in a browser. Go back and
do that now; it is the part of [Phase 4](phase-4-service-mesh.md) you could not run yet.

**Next: [Phase 6 — Operating it](phase-6-operating.md).** Now find out what happens when it breaks.

[← All phases](README.md) · [← Phase 5 — Making it someone else's platform](phase-5-developer-portal.md) · [Phase 6 — Operating it, and taking it down →](phase-6-operating.md)

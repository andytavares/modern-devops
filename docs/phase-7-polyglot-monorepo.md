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

This phase replaces both with a monorepo build system (Pants) and a real interface definition. The
test of whether it worked: **change a field in a `.proto` and watch two languages fail in the same
command, on your laptop, before anything reaches a cluster.**

> **Phase 7 sits before Phase 6 when reading.** Phase 6 ends by deleting the cluster; nothing
> sensibly comes after that. See [Why this order](README.md#why-this-order).

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

Five of the eight are experimental in Pants 2.33.0. That is a real risk and it is taken
knowingly: the entire value of a polyglot monorepo is that one tool builds everything, so refusing the
experimental backends means not doing this at all. The mitigation is that **every one of them has a
one-command escape hatch** — `go build`, `npm run build`, `ruff check` — because Pants delegates to
the language's own toolchain rather than reimplementing it. If a backend breaks on upgrade, you lose
orchestration, not the ability to ship.

### 17.3 `pants.toml`

Pants 2.x is **not** on PyPI. It ships as `scie-pants`, a self-bootstrapping launcher binary that
reads `pants_version` out of `pants.toml` and fetches the matching Pants itself. Install the launcher
from its GitHub release, checksum-verified:

```bash
# Download to a temp path and verify BEFORE it goes on PATH. A checksum
# checked *after* installation has already installed the thing.
curl -fsSL -o /tmp/scie-pants \
  https://github.com/pantsbuild/scie-pants/releases/download/v0.13.2/scie-pants-macos-aarch64
echo "a6f3231413ca1f793caffa621171a4b1a0158e7488cd0b5bb3e742cb99cc72a8  /tmp/scie-pants" \
  | shasum -a 256 -c -
# /tmp/scie-pants: OK

# /usr/local/bin is root:wheel on macOS, so this needs sudo — and `install`
# sets the mode in the same step, so there is no window where the file is on
# PATH without one.
sudo install -m 755 /tmp/scie-pants /usr/local/bin/pants
rm /tmp/scie-pants

command -v pants
```

> [!warning] **`curl -o /usr/local/bin/pants` without `sudo` fails, and the error names neither.**
> `/usr/local/bin` is `root:wheel` on macOS. curl reports
> `curl: (56) Failure writing output to destination, passed 16375 returned 4294967295` — a libcurl
> write error with a 32-bit unsigned `-1` in it, which reads like a network fault. The next line then
> fails on a file that was never created. The whole thing is a permission denied wearing a costume.
>
> `pants --version` is deliberately not the check here: `scie-pants` reads `pants_version` out of
> `pants.toml`, which does not exist until the next command, so it would fail for an unrelated reason.
> `command -v pants` is what proves the install.

> **This one binary comes from outside the choke point, deliberately and once.** Everything Pants
> then resolves — Python wheels, Go modules — goes through Nexus
> ([§5.1](phase-0-foundations.md#51-what-nexus-is-actually-for)), and CI does not repeat this
> download at all: `.buildkite/pants-ci.Dockerfile` bakes the same checksum-verified launcher into an
> image that lives in Nexus ([§19.5](#195-one-ci-step-instead-of-two)). A pinned, hashed, one-time
> fetch is an honest compromise; `curl … | bash` on every build is not.

**`pants.toml`**

```toml
[GLOBAL]
pants_version = "2.33.0"

# One build system, four languages. The Python and protobuf-Python backends are
# stable; go, javascript and typescript are still shipped under
# `pants.backend.experimental.*` upstream. That is a real risk and it is taken
# knowingly: the value of a polyglot monorepo is precisely that one tool builds,
# tests and lints everything, and the escape hatch for any of them is the
# language's own toolchain, one command away.
backend_packages = [
  # Python — stable (ruff lives under experimental.* in 2.33, mypy does not)
  "pants.backend.python",
  "pants.backend.experimental.python.lint.ruff.check",
  "pants.backend.experimental.python.lint.ruff.format",
  "pants.backend.python.typecheck.mypy",
  "pants.backend.codegen.protobuf.python",

  # Go — experimental upstream
  "pants.backend.experimental.go",
  "pants.backend.experimental.codegen.protobuf.go",

  # Frontend — experimental upstream
  "pants.backend.experimental.javascript",
  "pants.backend.experimental.typescript",
]

# Everything that is not source. dist/ holds `pants package` output — the PEXes
# and Go binaries that Buildah later copies into images.
pants_ignore.add = [
  # Scaffolder templates, not source. Their BUILD files contain nunjucks
  # placeholders and are not valid Python until Backstage renders them —
  # Pants would otherwise fail the whole repo with a BuildFileSyntaxError.
  "/deploy/backstage/templates",
  "/portal",          # Backstage owns its own Yarn workspace; not ours to build
  "/modern-devops-wiki",
  "/raw",
  # Pants honours only the root .gitignore — `--pants-ignore-use-gitignore`
  # "does not yet support reading nested gitignore files" — so frontend/.gitignore
  # does not reach it and `pants tailor` walks into installed packages and build
  # output.
  "/frontend/node_modules",
  "/frontend/dist",
]
# `/docs` is deliberately NOT ignored: `checks/` reads the phase files to
# assemble the single-file edition and to verify every listing still matches
# the file it names, so Pants has to be able to see them.

[source]
# Import roots. `protos` is listed so generated code is importable as
# `shop.v1.pricing_pb2` rather than by a path that leaks the directory layout.
root_patterns = ["/", "/services/*", "/protos"]

[python]
interpreter_constraints = [">=3.13,<3.14"]
enable_resolves = true
default_resolve = "python-default"

[python.resolves]
python-default = "locks/python-default.lock"

[python-bootstrap]
# Where Pants looks for a CPython matching the interpreter constraints above.
# <PYENV> and <PATH> are the defaults; the Homebrew path is added because
# `brew install python@3.13` puts an unversioned `python` in libexec/bin that
# is not on PATH, and without it Pants reports
# "No working interpreter compatible with the requested constraints was found"
# while a perfectly good 3.13 sits on disk.
search_path = ["<PYENV>", "<PATH>", "/opt/homebrew/opt/python@3.13/libexec/bin"]

[python-repos]
# The supply-chain choke point (§5.1) applies to the build system too. Pants
# resolves through Nexus, not pypi.org, exactly like uv did before it.
indexes = ["http://nexus:8081/repository/pypi-proxy/simple"]

[golang]
# Pants defaults cgo_enabled to TRUE, which produces a dynamically linked
# binary needing /lib/ld-linux-aarch64.so.1. gcr.io/distroless/static has no
# libc and no linker, so the pod dies with:
#   exec /order-worker: no such file or directory
# — on a file that is present and executable, which is why it reads as a
# missing binary rather than a missing loader. The original hand-written
# Dockerfile set CGO_ENABLED=0 for exactly this reason; moving the build into
# Pants silently dropped it.
cgo_enabled = false

# Go modules resolve through Nexus. Nothing else is overridden here, and that
# is the point: `go.sum` records a hash for every module in the build list, so
# verification happens locally against it and never needs the checksum
# database. Turning GOSUMDB off would not speed that up — it would only disarm
# verification for the next dependency someone adds. If a genuinely private
# module ever arrives, the documented escape is scoped, not global:
# `GOPRIVATE=github.com/yourorg/*`.
#
# -mod=readonly is already Go's default; it is stated because it is
# load-bearing. Under -mod=mod a build may rewrite go.mod and succeed against a
# dependency set nobody committed.
subprocess_env_vars = [
  "GOPROXY=http://nexus:8081/repository/go-proxy",
  "GOFLAGS=-mod=readonly",
  "HOME",
  "PATH",
]

[python-protobuf]
# protoc also emits .pyi stubs for each generated file. Without this, mypy sees
# pricing_pb2.py building its message classes dynamically via
# _builder.BuildTopDescriptorsAndMessages(...) into globals() and reports
# "PriceOrderRequest is not defined" — the classes genuinely do not exist
# statically. Pants' help prefers this over the older mypy_plugin option.
generate_type_stubs = true

[mypy]
install_from_resolve = "python-default"

[test]
# A test that depends on network or wall-clock is a test that fails in CI at
# 2am for reasons unrelated to the change. Fail loudly instead.
timeout_default = 60

[anonymous-telemetry]
enabled = false
```

The non-obvious lines:

- **Ruff's backend path is `pants.backend.experimental.python.lint.ruff.check` / `.format`.** In 2.33
  there is no non-experimental ruff backend to point at.
- **`[mypy] install_from_resolve` but no `[ruff]` equivalent.** mypy is a resolved Python package and
  belongs in the lockfile; ruff is a downloaded binary and does not.
- **`pants_ignore` excludes `/deploy/backstage/templates` and `/portal`.** The scaffolder skeleton's
  `BUILD` file contains nunjucks placeholders and is not valid Python until Backstage renders it;
  Backstage's own Yarn workspace is not ours to build
  ([§14.8](phase-5-developer-portal.md#148-build-and-deploy-the-portal)).
- **`/frontend/node_modules` and `/frontend/dist` are listed because Pants reads only the root
  `.gitignore`.** `--pants-ignore-use-gitignore` does not descend into nested ignore files, so
  `frontend/.gitignore` never reaches Pants and `pants tailor` walks into installed packages and
  build output. `/docs` is deliberately *not* ignored: `checks/` reads the phase files to assemble the
  single-file edition, so Pants has to be able to see them.
- **`[python-bootstrap] search_path` names the Homebrew path explicitly.** `brew install python@3.13`
  puts the unversioned `python` in `libexec/bin`, which is deliberately off `PATH`, and Pants' default
  search will not find it. `<PYENV>` and `<PATH>` are the defaults and must be repeated, not replaced.
- **`[python-repos]` and `[golang]` both point at Nexus**, for the same reason `uv` did
  ([§5.1](phase-0-foundations.md#51-what-nexus-is-actually-for)). Nothing else is overridden, and that
  is the point: checksum verification stays on, because `go.sum` records a hash for every module in
  the build list and the `go` command verifies against it locally
  ([§5.1](phase-0-foundations.md#51-what-nexus-is-actually-for) is blunt about why `GOSUMDB=off`
  behind a private proxy is the wrong reflex). `-mod=readonly` is already Go's default and is stated
  because it is load-bearing: under `-mod=mod` a build may rewrite `go.mod` and succeed against a
  dependency set nobody committed.
- **`[golang] cgo_enabled = false` is mandatory.** Pants defaults it to *true*, which links
  `order-worker` dynamically against libc. `gcr.io/distroless/static-debian12` has neither libc nor a
  dynamic loader, so the pod dies with `exec /order-worker: no such file or directory` on a file that
  is present and executable.
- **`enable_resolves` with a single named lockfile** means every Python target in the repo resolves
  against `locks/python-default.lock`. One lock, one resolution, no chance of two services
  disagreeing about `protobuf`. Pants still computes per-target dependencies from imports, so a
  service ships only what it imports — one requirements file does not mean one fat artifact.
- **`generate_type_stubs`** is [§18.3](#183-why-protoc-must-emit-pyi-stubs).

**Declare the third-party Python before you lock it.** `generate-lockfiles` resolves the requirements
Pants can see, and it can see none until a `python_requirements` target points at a file. Run it now
and it stops with `ValueError: Cannot generate lockfile with no requirements. Please add some
requirements to python-default.`

**`3rdparty/python/requirements.txt`**

```
# Third-party Python for the whole monorepo, resolved once into
# locks/python-default.lock. Pants computes per-target dependencies from
# imports, so a service only ships what it actually uses — one requirements
# file does not mean one fat PEX.
#
# Versions are pinned by the lockfile, which is committed. Pinning here as well
# would mean two places to update and one of them silently winning.

# --- gRPC + protobuf runtime (generated code needs these at run time) ---
grpcio
grpcio-tools
protobuf
# The health checking protocol and server reflection are first-party gRPC
# add-ons, shipped as separate packages by design. Health is what Kubernetes'
# `grpc:` probe and grpc_health_probe speak; reflection is what lets grpcurl
# talk to a server without a local copy of the .proto.
grpcio-health-checking
grpcio-reflection

# --- order-api ---
fastapi[standard]==0.139.2
aiokafka==0.12.0
boto3==1.40.11
prometheus-client==0.23.1
pydantic==2.11.7
# FastAPI documents pydantic-settings for exactly the job settings.py was doing
# by hand: parse the environment, cast it, validate it, and report every missing
# variable at once instead of only the first.
pydantic-settings==2.7.1

# --- test + typecheck ---
pytest==8.4.1
httpx==0.28.1
mypy
types-protobuf
# grpcio ships no py.typed marker, so mypy cannot see its types at all. Verified
# via `pants export --resolve=python-default` that site-packages has no py.typed
# under grpc/ — mypy's own suggestion to install these stubs is correct.
types-grpcio
```

**`3rdparty/python/BUILD`**

```python
python_requirements(
    name="reqs",
    source="requirements.txt",
)
```

> **One requirements file for the whole monorepo, and everything is here from the start.** The
> packages this phase has not explained yet — `pydantic-settings` in
> [§18.6](#186-order-api-calls-pricing), the two gRPC add-ons in
> [§19.4](#194-the-grpc-server-health-checking-and-reflection), `types-grpcio` — are in the list now
> so the lockfile is generated **once**. Adding a requirement later means re-running
> `generate-lockfiles` and committing a new lock, which is the right workflow on a real repo and pure
> friction in a tutorial. The comments in the file say what each group is for; the sections below say
> why.

Pants writes its caches and its build output into the repo, so extend the root `.gitignore` before
the next `git add`. Without `.pants.d/`, a `git add -A` commits a daemon's pid files and a
several-hundred-megabyte local cache.

**`.gitignore`**

```
.venv/
__pycache__/
bin/
*.pyc
.DS_Store

# Pants build output
/dist/
.pants.d/
.pids/
__pycache__/

# `go build` inside a service directory drops a binary named after the module,
# next to the source. A 27MB compiled binary was tracked here for exactly that
# reason.
/services/order-worker/order-worker
```

> **Pants reads only the root `.gitignore`.** `--pants-ignore-use-gitignore` "does not yet support
> reading nested gitignore files", so a `frontend/.gitignore` never reaches Pants and `tailor` walks
> into `node_modules` ([§17.4](#174-source-roots-and-the-duplicate-module-trap)). This is the one that
> matters, which is why every ignore in this build lives here.

Now generate the lockfile and commit it:

```bash
pants generate-lockfiles --resolve=python-default
git add .gitignore locks/python-default.lock 3rdparty/python
```

### 17.4 Source roots, and the duplicate-module trap

`root_patterns = ["/", "/services/*", "/protos"]` declares the import roots. `/services/*` means
each service directory is its own root, so `services/order-api/order_api/main.py` is importable as
`order_api.main`. `/protos` means generated code is importable as `shop.v1.pricing_pb2` rather than by
a path that leaks the directory layout.

That second root is worth doing deliberately. Without it, both services would import their shared
contract by a path — and a path is a thing that changes when someone reorganises a directory.

One rule follows from that layout, and it is not optional: **every service needs a unique top-level
package name.** A shared `/services/*` source root puts them all in the same module namespace, so two
services shipping their code in `app/` — the FastAPI tutorial convention — become the same module
`app`. mypy does not degrade there, it refuses to run at all (`Duplicate module named "app"`), and
Pants cannot infer intra-service imports either, because `from app.settings import settings` is
genuinely ambiguous.

So the packages are named for their services:

```
services/order-api/order_api/     # main.py, settings.py
services/pricing/pricing/         # main.py
```

Underscores, not hyphens: service names are hyphenated and Python packages may not be. The Backstage
skeleton ([§14.6](phase-5-developer-portal.md#146-paved-path-1--a-new-service)) templates its package
directory as `${{ values.name | replace('-', '_') }}` for exactly this reason, so a scaffolded
`quotes-api` arrives with a `quotes_api/` package and collides with nothing.

### 17.5 Targets, and the two files that decide whether the checks pass

Pants needs a `BUILD` file per source directory. `pants tailor ::` will generate skeletons, and they
are not what this repo runs — tailor writes one `BUILD` per directory and has no way to know which
binary is deployable or where its artifact should land. Write them:

**`services/order-api/BUILD`**

```python
python_sources(
    name="lib",
    sources=["order_api/**/*.py"],
)

python_tests(
    name="tests",
    # `!tests/__init__.py`: it's a namespace marker, not a test — including it
    # makes Pants generate a `python_test` target for it that pytest then fails
    # with "no tests collected".
    sources=["tests/**/*.py", "!tests/__init__.py"],
    dependencies=[":lib"],
)

pex_binary(
    name="bin",
    # Declares this target as something CI ships. `pants --tag=deployable
    # package ::` selects on it, so a service is packaged the moment it says
    # so itself — no list in the pipeline to keep in sync.
    tags=["deployable"],
    entry_point="order_api.main:main",
    dependencies=[":lib"],
    # Land in dist/ under a predictable name so dist/ can be used directly as
    # the Buildah build context and the Dockerfile can COPY by name. Default
    # would be dist/services.order-api/bin.pex.
    output_path="order-api.pex",
)
```

**`services/order-worker/BUILD`**

```python
go_binary(
    name="bin",
    tags=["deployable"],
    output_path="order-worker",
)

go_mod()

go_package(
    name="order-worker0",
)
```

> **`go_package(name="order-worker0")` is tailor's name and it is kept on purpose.** Pants generates
> it when the module and the package share a directory, and renaming it means renaming it in every
> reference. The `0` is ugly and it is not a mistake.

Now the type checker. mypy fails on the first run without this, on three of `order-api`'s
dependencies — `boto3`, `botocore` and `aiokafka` publish no `py.typed` marker and no stubs exist for
them:

```
services/order-api/order_api/main.py:11: error: Skipping analyzing "boto3": module is
  installed, but missing library stubs or py.typed marker  [import-untyped]
```

**`mypy.ini`**

```ini
[mypy]
# Pants discovers this file automatically ([mypy].config_discovery defaults to
# true). Everything below is a PER-MODULE exception with a stated reason — there
# is deliberately no global ignore_missing_imports, because that would silence
# real typos in our own imports as well as third-party gaps.

[mypy-google.protobuf.*]
# types-protobuf IS in the resolve, but stub packages are never *imported*, so
# Pants cannot infer them as a dependency of any target and they never land in
# mypy's sandbox. Pants 2.33's [mypy] exposes only `skip` and `args` — there is
# no extra_type_stubs lever. The generated .pyi files import google.protobuf,
# so without this every protobuf-using target fails on generated code we do not
# write.
ignore_missing_imports = true

[mypy-aiokafka.*]
# aiokafka publishes no py.typed marker and no stubs package exists on PyPI.
# Nothing to install; this is the honest state of the dependency.
ignore_missing_imports = true

[mypy-boto3.*]
# boto3/botocore are untyped at runtime. boto3-stubs exists and would be a real
# improvement, but it is a large dependency and pulling it in is a deliberate
# decision rather than a side effect of this migration. Tracked, not hidden.
ignore_missing_imports = true

[mypy-botocore.*]
ignore_missing_imports = true

[mypy-yaml]
# pyyaml is a dependency of the CI *image*, not of the Python resolve:
# checks/verify_chart.py runs as a plain script against a rendered chart, not
# through Pants, so pyyaml is installed in .buildkite/pants-ci.Dockerfile
# instead. mypy therefore has nothing to import here.
ignore_missing_imports = true
```

> **Every exception is per-module and carries its reason.** A global `ignore_missing_imports = true`
> at the top would make all three errors disappear — along with every typo in your *own* import
> statements, which is the entire class of error mypy is here to catch. The rule worth taking from
> this file: **an exception you cannot write a sentence to justify is an exception you should not
> take.**

### 17.6 One command, and what it actually does

`ruff` reformats the Python written in [§3.1](phase-1-the-application.md#31-order-api-python--fastapi),
which was never run through it. So the first thing is a format, not a check — otherwise the command
below fails on `ruff format` and never reaches the type checker or the tests:

```bash
pants fmt ::
# + ruff format made changes.

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

**`protos/shop/v1/pricing.proto`**

```protobuf
syntax = "proto3";

package shop.v1;

// One .proto, two languages, one build system. Pants generates Python stubs for
// order-api and pricing, and Go stubs for order-worker, from this single file —
// which is the entire argument for a polyglot monorepo. Change a field here and
// both languages fail to compile in the same `pants check ::`, before anything
// reaches a cluster.
option go_package = "github.com/andytavares/modern-devops/protos/shop/v1;shopv1";

service Pricing {
  // Priced synchronously on the order path, which is what makes it a useful
  // subject for §9: a timeout here is a user-visible failure, so retries,
  // outlier detection and traffic shifting all have observable consequences.
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

  // Which pricing implementation served this call. The frontend tallies it, so
  // a VirtualService weight change is visible in a browser within seconds
  // rather than only in Kiali. This field is the whole canary demo.
  string served_by = 4;
}
```

`served_by` is the field the rest of this platform is built around: the pricing implementation writes
its own version into it, `order-api` passes it through, and the frontend
([§19.4](#194-the-frontend-vite-and-a-live-tally)) tallies it. That is what makes an Istio weight
change something you watch in a browser rather than infer from a metric.

Money is `int32` cents throughout. Floating-point currency is a bug you ship once.

**`protos/shop/v1/BUILD`**

```python
# grpc=True generates the service stubs, not just the messages. One target feeds
# both language backends — Python via pants.backend.codegen.protobuf.python and
# Go via pants.backend.experimental.codegen.protobuf.go.
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

`services/pricing` serves `shop.v1.Pricing/PriceOrder` on port 50051. On that same port it also
registers two first-party gRPC services: the **health checking protocol** (`grpc.health.v1`) and
**server reflection**. Port 9090 carries Prometheus metrics and nothing else, from
`prometheus_client.start_http_server()`.

There is no hand-rolled HTTP server here and there must not be one. A gRPC server that answers probes
over a second protocol on a second port is asserting that the HTTP listener and the gRPC listener fail
together, which is not true — a saturated gRPC thread pool leaves the HTTP thread answering `200` for a
server that cannot serve an RPC. The kubelet speaks the health checking protocol itself
([§19.3](#193-a-pex-needs-somewhere-to-write-and-readonlyrootfilesystem-gives-it-nowhere)), so the
probe and the traffic take the same path. Reflection is what lets `grpcurl` call the server without a
local copy of the `.proto`.

**`services/pricing/pricing/main.py`**

```python
import logging
import signal
import sys
import time
from concurrent import futures
from types import FrameType

import grpc

# typeshed publishes types-grpcio-health-checking and types-grpcio-reflection,
# but neither is in 3rdparty/python/requirements.txt, so mypy has nothing to
# read. The ignore is per-import and per-error-code: it silences these two
# packages and nothing else.
from grpc_health.v1 import (  # type: ignore[import-untyped]
    health,
    health_pb2,
    health_pb2_grpc,
)
from grpc_reflection.v1alpha import reflection  # type: ignore[import-untyped]
from prometheus_client import Counter, Histogram, start_http_server
from shop.v1 import pricing_pb2, pricing_pb2_grpc

from .settings import settings  # pants: no-infer-dep (already colocated in this target)

# ---------- logging ----------
logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format='{"ts":"%(asctime)s","level":"%(levelname)s","msg":"%(message)s"}',
)
log = logging.getLogger("pricing")

# ---------- metrics ----------
PRICING_REQUESTS = Counter(
    "pricing_requests_total",
    "Priced orders, by rule and serving version",
    ["rule", "version"],
)
PRICING_DURATION = Histogram(
    "pricing_request_duration_seconds", "Time to price one order"
)

# Service names are read off the generated descriptors rather than written out
# as string literals, so renaming a service in the .proto cannot leave a stale
# name registered with health checking or reflection.
PRICING_SERVICE_NAME = pricing_pb2.DESCRIPTOR.services_by_name["Pricing"].full_name
HEALTH_SERVICE_NAME = health_pb2.DESCRIPTOR.services_by_name["Health"].full_name

# Seconds in-flight RPCs get to finish after SIGTERM before they are aborted.
SHUTDOWN_GRACE_SECONDS = 5


def calculate_price(
    quantity: int, unit_amount_cents: int, version: str
) -> tuple[int, int, str]:
    """Pure pricing logic, version-switched.

    v1: list price, no discount.
    v2: same, but a 3+ quantity line gets 10% off (integer math, rounded down).
    """
    list_total = unit_amount_cents * quantity
    discount_cents = 0
    rule_applied = "list-price"
    if version == "v2" and quantity >= 3:
        discount_cents = (list_total * 10) // 100
        rule_applied = "bulk-10pct"
    return list_total - discount_cents, discount_cents, rule_applied


def validate_request(sku: str, quantity: int, unit_amount_cents: int) -> None:
    """Raises ValueError with a useful message on invalid input."""
    if not sku:
        raise ValueError("sku must not be empty")
    if quantity < 1:
        raise ValueError(f"quantity must be >= 1, got {quantity}")
    if unit_amount_cents < 1:
        raise ValueError(f"unit_amount_cents must be >= 1, got {unit_amount_cents}")


class PricingServicer(pricing_pb2_grpc.PricingServicer):
    def PriceOrder(
        self, request: pricing_pb2.PriceOrderRequest, context: grpc.ServicerContext
    ) -> pricing_pb2.PriceOrderResponse:
        started = time.perf_counter()
        try:
            validate_request(request.sku, request.quantity, request.unit_amount_cents)
        except ValueError as exc:
            # abort() raises, so it terminates the RPC in one call and cannot be
            # followed by an accidental successful return.
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(exc))

        total_amount_cents, discount_cents, rule_applied = calculate_price(
            request.quantity, request.unit_amount_cents, settings.version
        )

        PRICING_REQUESTS.labels(rule=rule_applied, version=settings.version).inc()
        PRICING_DURATION.observe(time.perf_counter() - started)
        log.info(
            "priced sku=%s quantity=%d rule=%s served_by=%s",
            request.sku,
            request.quantity,
            rule_applied,
            settings.version,
        )
        return pricing_pb2.PriceOrderResponse(
            total_amount_cents=total_amount_cents,
            discount_cents=discount_cents,
            rule_applied=rule_applied,
            served_by=settings.version,
        )


def build_server() -> tuple[grpc.Server, health.HealthServicer]:
    """Assemble the gRPC server: pricing, health checking and reflection.

    Nothing here binds a port or starts a thread, so tests can build the exact
    server the process runs and drive it on an ephemeral port.
    """
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    pricing_pb2_grpc.add_PricingServicer_to_server(PricingServicer(), server)

    # The non-blocking servicer answers Watch from its own pool instead of
    # parking a request thread per watcher, which is what the gRPC health
    # example uses.
    health_servicer = health.HealthServicer(
        experimental_non_blocking=True,
        experimental_thread_pool=futures.ThreadPoolExecutor(max_workers=10),
    )
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)
    # The protocol requires the server to register every service explicitly,
    # including the empty service name that carries overall server health. A
    # name that is not registered gets NOT_FOUND, not NOT_SERVING, so anything
    # a probe may ask for has to be set here.
    for service_name in ("", PRICING_SERVICE_NAME):
        health_servicer.set(service_name, health_pb2.HealthCheckResponse.SERVING)

    # Python reflection has no automatic service discovery: every service the
    # server exposes has to be named, including reflection itself. Without this,
    # grpcurl needs a local copy of the .proto to call anything.
    reflection.enable_server_reflection(
        (PRICING_SERVICE_NAME, HEALTH_SERVICE_NAME, reflection.SERVICE_NAME),
        server,
    )
    return server, health_servicer


def serve() -> None:
    server, health_servicer = build_server()
    server.add_insecure_port(f"[::]:{settings.grpc_port}")

    # prometheus_client's own server, in a daemon thread, is the documented way
    # to expose metrics from a process that is not a web application.
    start_http_server(settings.http_port)
    server.start()

    log.info(
        "pricing started version=%s grpc_port=%d metrics_port=%d",
        settings.version,
        settings.grpc_port,
        settings.http_port,
    )

    def handle_sigterm(signum: int, frame: FrameType | None) -> None:
        log.info("received signal %d, shutting down", signum)
        # Flips every registered service to NOT_SERVING and fails later Check
        # calls, so readiness probes see the pod leaving before the listener
        # disappears.
        health_servicer.enter_graceful_shutdown()
        server.stop(SHUTDOWN_GRACE_SECONDS)

    signal.signal(signal.SIGTERM, handle_sigterm)

    server.wait_for_termination()
    log.info("pricing stopped")


def main() -> None:
    serve()


if __name__ == "__main__":
    main()
```

`main.py` imports its configuration, and the package needs its marker files — Pants infers targets
from imports, and a package without `__init__.py` is not importable under the `/services/*` source
root:

**`services/pricing/pricing/settings.py`**

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Config from the environment.

    pydantic-settings does the parsing, casting and validation, and reports
    every bad or missing variable at once instead of only the first.
    """

    # Every variable this service reads is prefixed, so the field names stay
    # short and nothing here can collide with an unprefixed cluster variable.
    model_config = SettingsConfigDict(env_prefix="PRICING_")

    grpc_port: int = 50051
    http_port: int = 9090
    version: str = "v1"


settings = Settings()
```

**`services/pricing/pricing/__init__.py`** is empty, and so is
**`services/pricing/tests/__init__.py`**:

```bash
mkdir -p services/pricing/pricing services/pricing/tests
touch services/pricing/pricing/__init__.py services/pricing/tests/__init__.py
```

**`services/pricing/tests/test_pricing.py`**

```python
from collections.abc import Iterator

import grpc
import pytest
from grpc_health.v1 import health_pb2, health_pb2_grpc  # type: ignore[import-untyped]
from grpc_reflection.v1alpha import (  # type: ignore[import-untyped]
    reflection,
    reflection_pb2,
    reflection_pb2_grpc,
)
from shop.v1 import pricing_pb2, pricing_pb2_grpc

from pricing.main import (
    HEALTH_SERVICE_NAME,
    PRICING_SERVICE_NAME,
    build_server,
    calculate_price,
    validate_request,
)
from pricing.settings import Settings


class TestCalculatePriceV1:
    def test_no_discount_regardless_of_quantity(self) -> None:
        total, discount, rule = calculate_price(
            quantity=5, unit_amount_cents=1000, version="v1"
        )
        assert total == 5000
        assert discount == 0
        assert rule == "list-price"

    def test_single_unit(self) -> None:
        total, discount, rule = calculate_price(
            quantity=1, unit_amount_cents=250, version="v1"
        )
        assert total == 250
        assert discount == 0
        assert rule == "list-price"


class TestCalculatePriceV2:
    def test_discounts_at_quantity_three(self) -> None:
        total, discount, rule = calculate_price(
            quantity=3, unit_amount_cents=1000, version="v2"
        )
        assert discount == 300  # 10% of 3000
        assert total == 2700
        assert rule == "bulk-10pct"

    def test_discounts_above_quantity_three(self) -> None:
        total, discount, rule = calculate_price(
            quantity=10, unit_amount_cents=999, version="v2"
        )
        assert discount == 999  # floor(9990 * 0.10)
        assert total == 9990 - 999
        assert rule == "bulk-10pct"

    def test_no_discount_below_quantity_three(self) -> None:
        total, discount, rule = calculate_price(
            quantity=2, unit_amount_cents=1000, version="v2"
        )
        assert total == 2000
        assert discount == 0
        assert rule == "list-price"

    def test_discount_rounds_down(self) -> None:
        # list_total = 3 * 101 = 303; 10% = 30.3 -> floor to 30
        total, discount, rule = calculate_price(
            quantity=3, unit_amount_cents=101, version="v2"
        )
        assert discount == 30
        assert total == 273
        assert rule == "bulk-10pct"


def test_served_by_reflects_version() -> None:
    # calculate_price itself doesn't set served_by (that's the servicer's job),
    # but the version argument it's given is what would end up in served_by.
    _, _, rule_v1 = calculate_price(quantity=3, unit_amount_cents=1000, version="v1")
    _, _, rule_v2 = calculate_price(quantity=3, unit_amount_cents=1000, version="v2")
    assert rule_v1 == "list-price"
    assert rule_v2 == "bulk-10pct"


class TestValidateRequest:
    def test_valid_request_does_not_raise(self) -> None:
        validate_request(sku="widget-1", quantity=1, unit_amount_cents=1)

    def test_empty_sku_raises(self) -> None:
        with pytest.raises(ValueError, match="sku"):
            validate_request(sku="", quantity=1, unit_amount_cents=100)

    def test_zero_quantity_raises(self) -> None:
        with pytest.raises(ValueError, match="quantity"):
            validate_request(sku="widget-1", quantity=0, unit_amount_cents=100)

    def test_negative_quantity_raises(self) -> None:
        with pytest.raises(ValueError, match="quantity"):
            validate_request(sku="widget-1", quantity=-1, unit_amount_cents=100)

    def test_zero_unit_amount_raises(self) -> None:
        with pytest.raises(ValueError, match="unit_amount_cents"):
            validate_request(sku="widget-1", quantity=1, unit_amount_cents=0)

    def test_negative_unit_amount_raises(self) -> None:
        with pytest.raises(ValueError, match="unit_amount_cents"):
            validate_request(sku="widget-1", quantity=1, unit_amount_cents=-5)


class TestSettings:
    def test_reads_prefixed_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PRICING_GRPC_PORT", "50999")
        monkeypatch.setenv("PRICING_HTTP_PORT", "9111")
        monkeypatch.setenv("PRICING_VERSION", "v2")
        loaded = Settings()
        assert loaded.grpc_port == 50999
        assert loaded.http_port == 9111
        assert loaded.version == "v2"

    def test_ports_are_coerced_to_int(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PRICING_GRPC_PORT", "50051")
        assert Settings().grpc_port == 50051

    def test_non_numeric_port_is_rejected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("PRICING_GRPC_PORT", "not-a-port")
        with pytest.raises(ValueError, match="grpc_port"):
            Settings()


@pytest.fixture
def channel() -> Iterator[grpc.Channel]:
    """The real server, on an ephemeral port, over a real channel.

    Health checking and reflection are wire protocols; asserting on them from
    inside the process would prove nothing about what a kubelet or grpcurl sees.
    """
    server, _ = build_server()
    port = server.add_insecure_port("[::]:0")
    server.start()
    with grpc.insecure_channel(f"localhost:{port}") as chan:
        yield chan
    server.stop(None).wait()


class TestHealthChecking:
    def test_pricing_service_reports_serving(self, channel: grpc.Channel) -> None:
        stub = health_pb2_grpc.HealthStub(channel)
        response = stub.Check(
            health_pb2.HealthCheckRequest(service="shop.v1.Pricing"), timeout=5
        )
        assert response.status == health_pb2.HealthCheckResponse.SERVING

    def test_overall_health_reports_serving(self, channel: grpc.Channel) -> None:
        # The empty service name is the server's overall status, and it is what
        # a `grpc:` probe with no `service:` field asks for.
        stub = health_pb2_grpc.HealthStub(channel)
        response = stub.Check(health_pb2.HealthCheckRequest(service=""), timeout=5)
        assert response.status == health_pb2.HealthCheckResponse.SERVING

    def test_unregistered_service_is_not_found(self, channel: grpc.Channel) -> None:
        stub = health_pb2_grpc.HealthStub(channel)
        with pytest.raises(grpc.RpcError) as excinfo:
            stub.Check(health_pb2.HealthCheckRequest(service="shop.v1.Nope"), timeout=5)
        assert excinfo.value.code() == grpc.StatusCode.NOT_FOUND

    def test_graceful_shutdown_flips_every_service(self) -> None:
        server, health_servicer = build_server()
        port = server.add_insecure_port("[::]:0")
        server.start()
        try:
            with grpc.insecure_channel(f"localhost:{port}") as chan:
                stub = health_pb2_grpc.HealthStub(chan)
                health_servicer.enter_graceful_shutdown()
                for service_name in ("", "shop.v1.Pricing"):
                    response = stub.Check(
                        health_pb2.HealthCheckRequest(service=service_name), timeout=5
                    )
                    assert response.status == health_pb2.HealthCheckResponse.NOT_SERVING
        finally:
            server.stop(None).wait()


class TestReflection:
    def test_lists_pricing_health_and_reflection(self, channel: grpc.Channel) -> None:
        stub = reflection_pb2_grpc.ServerReflectionStub(channel)
        responses = stub.ServerReflectionInfo(
            iter([reflection_pb2.ServerReflectionRequest(list_services="")]),
            timeout=5,
        )
        listed = {
            service.name
            for response in responses
            for service in response.list_services_response.service
        }
        assert PRICING_SERVICE_NAME in listed
        assert HEALTH_SERVICE_NAME in listed
        assert reflection.SERVICE_NAME in listed


class TestPriceOrderRpc:
    def test_valid_request_is_priced(self, channel: grpc.Channel) -> None:
        stub = pricing_pb2_grpc.PricingStub(channel)
        response = stub.PriceOrder(
            pricing_pb2.PriceOrderRequest(
                sku="widget-1", quantity=1, unit_amount_cents=250
            ),
            timeout=5,
        )
        assert response.total_amount_cents == 250
        assert response.rule_applied == "list-price"

    def test_invalid_request_aborts_with_invalid_argument(
        self, channel: grpc.Channel
    ) -> None:
        # abort() must terminate the RPC. set_code/set_details followed by a
        # return would arrive here as a successful empty response instead.
        stub = pricing_pb2_grpc.PricingStub(channel)
        with pytest.raises(grpc.RpcError) as excinfo:
            stub.PriceOrder(
                pricing_pb2.PriceOrderRequest(
                    sku="", quantity=1, unit_amount_cents=250
                ),
                timeout=5,
            )
        assert excinfo.value.code() == grpc.StatusCode.INVALID_ARGUMENT
        details = excinfo.value.details()
        assert details is not None
        assert "sku" in details
```

**`services/pricing/Dockerfile`** — the same shape as the other two services, and the file
[§19.5](#195-one-ci-step-instead-of-two)'s discovery loop looks for to decide that `pricing` is a
service CI should build at all:

```dockerfile
# syntax=docker/dockerfile:1.7
#
# Build context is `dist/` (the `pants package services/pricing:bin` output),
# not the source tree: the PEX already bundles the interpreter-independent
# dependency closure resolved by Pants from locks/python-default.lock, so there
# is nothing left for this image to resolve or install.
FROM docker.io/library/python:3.13-slim

RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin appuser

WORKDIR /app
COPY --chown=10001:10001 pricing.pex /app/pricing.pex

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER 10001
# 50051 gRPC (application, health checking and reflection), 9090 Prometheus
# metrics. Probes speak the gRPC health protocol on 50051, not HTTP.
EXPOSE 50051 9090
ENTRYPOINT ["python", "/app/pricing.pex"]
```


Three things are load-bearing:

- **Every service name is registered explicitly, including the empty one.** The empty name carries the
  server's overall health and is what a `grpc:` probe with no `service:` field asks for. A name that
  was never registered answers `NOT_FOUND`, not `NOT_SERVING`, so anything a probe may ask for has to
  be `set()` here.
- **Service names come off the generated descriptors**, `pricing_pb2.DESCRIPTOR.services_by_name[...]`,
  not string literals. Renaming a service in the `.proto` then cannot leave a stale name registered.
- **Reflection needs its own name in its own list.** Python's reflection has no automatic discovery;
  every service the server exposes is named by hand, `reflection.SERVICE_NAME` included.

`build_server` binds no port and starts no thread, which is what lets the tests stand up the exact
server the process runs on an ephemeral port. Health checking and reflection are wire protocols —
asserting on them in-process would prove nothing about what a kubelet or `grpcurl` sees.

On `SIGTERM`, `health_servicer.enter_graceful_shutdown()` flips every registered service to
`NOT_SERVING` before `server.stop()` closes the listener, so readiness sees the pod leaving while it
can still answer. The main thread then parks on `server.wait_for_termination()`.

`PriceOrder` rejects bad input with `context.abort(grpc.StatusCode.INVALID_ARGUMENT, ...)`. `abort()`
raises, so it ends the RPC in one call; `set_code`/`set_details` followed by a `return` arrives at the
caller as a *successful* empty response.

Config is `pydantic-settings` with `env_prefix="PRICING_"`, so `PRICING_GRPC_PORT`, `PRICING_HTTP_PORT`
and `PRICING_VERSION` are parsed, cast and validated by the library rather than by hand, and a
non-numeric port fails at startup naming the field.

Its behaviour is switched by `PRICING_VERSION` and echoed back in `served_by`:

- **v1** — list price. `total = unit_amount_cents × quantity`, no discount.
- **v2** — the same, except a line with `quantity >= 3` gets 10% off, integer math, rounded down.

That difference is chosen so an Istio weight change is *observable*. Two versions that behave
identically make a canary a matter of faith.

`order-api` calls it on the order path with a **2 second deadline**, using `grpc.aio` so a slow
pricing service cannot block the event loop. Failures are translated one gRPC status at a time —
`DEADLINE_EXCEEDED` → 504, `UNAVAILABLE` → 503, `INVALID_ARGUMENT` → 400, `RESOURCE_EXHAUSTED` → 429,
anything else → 502 — and every outcome increments `pricing_calls_total{result,served_by}`.

> **It does not fall back to a locally computed price, and that is a deliberate choice you should
> argue with.** A fallback is the kinder production design: the customer gets an order instead of an
> error. It is also the thing that would make every experiment in
> [§9.9](phase-4-service-mesh.md#99-canary-two-versions-of-pricing-behind-one-service) invisible — a
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

#### Wiring `order-api` to it

A pricing service nothing calls is a pricing service you cannot canary. The rest of this section is
the caller side: the address, the client, the metric, the call, and the tests. Do it now — everything
downstream ([§19.4](#194-the-frontend-vite-and-a-live-tally),
[§9.9](phase-4-service-mesh.md#99-canary-two-versions-of-pricing-behind-one-service)) depends on it.

**Address and deadlines.** `order-api`'s settings module is now a `pydantic-settings` `BaseSettings`
subclass. Hand-rolled environment parsing is the job that library exists to do, and it is the approach
FastAPI documents. Replace [§3.1](phase-1-the-application.md#31-order-api-python--fastapi)'s version
with this. `pydantic-settings` is already in `3rdparty/python/requirements.txt` and in the lock
([§17.3](#173-pantstoml)), so there is nothing to re-resolve:

**`services/order-api/order_api/settings.py`**

```python
"""Config from the environment, validated once at import.

pydantic-settings' `BaseSettings` is the approach FastAPI documents for this
(https://fastapi.tiangolo.com/advanced/settings/, and
https://docs.pydantic.dev/latest/concepts/pydantic_settings/). A field with no
default is required: if it is missing the process refuses to start, and pydantic
reports *every* missing or malformed variable at once rather than only the first.
Types are declared, not cast by hand.

Environment variable names match field names case-insensitively, so `kafka_topic`
reads `KAFKA_TOPIC`. Where the variable a field must read is not the upper-cased
field name, `validation_alias` pins the real name.
"""

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    kafka_brokers: str
    kafka_topic: str = "orders"

    s3_bucket: str
    # boto3 owns the name AWS_DEFAULT_REGION, so the field cannot simply be
    # called `default_region`; the alias binds the field to the variable boto3
    # and every AWS tool already expect.
    aws_region: str = Field(default="us-east-1", validation_alias="AWS_DEFAULT_REGION")
    aws_endpoint_url: str | None = None

    # Injected by External Secrets Operator from OpenBao. See §7. The alias keeps
    # the variable namespaced to this service while the field stays generic.
    signing_key: str = Field(validation_alias="ORDER_SIGNING_KEY")

    service_version: str = "dev"
    order_api_port: int = 8000

    pricing_addr: str = "pricing.shop.svc.cluster.local:50051"
    pricing_timeout_seconds: float = 2.0
    # Readiness must answer fast enough that a probe times out on the probe's
    # terms, not ours. Kept well under the order-path timeout above.
    pricing_health_timeout_seconds: float = 1.0


# pydantic's metaclass is a PEP 681 `dataclass_transform`, so mypy synthesises an
# `__init__` taking every field and reports the three required ones as missing
# arguments. They are not passed as arguments — BaseSettings reads them from the
# environment, which is the entire point of the class.
settings = Settings()  # type: ignore[call-arg]
```

A field with no default is required: the process refuses to start without it, which is the same
crash-loop-rather-than-degrade behaviour [§3.1](phase-1-the-application.md#31-order-api-python--fastapi)
argued for, now with every missing variable reported at once instead of only the first.

Three details are not guessable:

- **`validation_alias` is what binds a field to a variable name it does not derive.** `aws_region`
  would otherwise read `AWS_REGION`; boto3 and every AWS tool use `AWS_DEFAULT_REGION`, so the alias
  pins it. `signing_key` reads `ORDER_SIGNING_KEY` for the same reason — the variable stays namespaced
  to the service while the field stays generic.
- **`# type: ignore[call-arg]` on the instantiation is required, not sloppiness.** pydantic's metaclass
  is a PEP 681 `dataclass_transform`, so mypy synthesises an `__init__` taking every field and reports
  the required ones as missing arguments. They are not arguments; `BaseSettings` reads them from the
  environment, which is the whole point of the class.
- **The comparison is against the field name, not the variable name.** Matching is
  case-insensitive, so `kafka_topic` reads `KAFKA_TOPIC` with nothing declared.

`pricing_addr`'s default matches the `Service` the chart creates in [§19.3](#193-a-pex-needs-somewhere-to-write-and-readonlyrootfilesystem-gives-it-nowhere)
(`pricing`, namespace `shop`, port 50051), so `order-api.yaml` needs no new env entry. The timeout is
a setting rather than a constant because it is the number you tune when
[§9.9](phase-4-service-mesh.md#99-canary-two-versions-of-pricing-behind-one-service) starts injecting
delays. `pricing_health_timeout_seconds` is separate and shorter: readiness must answer on the probe's
schedule, not on the order path's.

**The client.** Add the imports and the metric to `main.py`:

**`services/order-api/order_api/main.py`**

```python
import hashlib
import hmac
import json
import logging
import sys
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import boto3
import grpc
import uvicorn  # pants: no-infer-dep  (via fastapi[standard])
from aiokafka import AIOKafkaProducer
from botocore.config import Config as BotoConfig  # pants: no-infer-dep  (via boto3)
from fastapi import FastAPI, HTTPException
from fastapi.concurrency import run_in_threadpool

# grpcio-health-checking ships no py.typed marker, so mypy cannot see the
# generated health stubs. Declared at the import rather than behind a global
# ignore_missing_imports, which would silence real typos as well.
from grpc_health.v1 import health_pb2, health_pb2_grpc  # type: ignore[import-untyped]
from prometheus_client import Counter, Histogram, make_asgi_app
from pydantic import BaseModel, Field

from shop.v1 import pricing_pb2, pricing_pb2_grpc

from .settings import settings

# ---------- logging ----------
logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format='{"ts":"%(asctime)s","level":"%(levelname)s","msg":"%(message)s"}',
)
log = logging.getLogger("order-api")

# ---------- metrics ----------
ORDERS_RECEIVED = Counter(
    "orders_received_total", "Orders accepted by the API", ["result"]
)
ORDER_LATENCY = Histogram(
    "order_ingest_duration_seconds", "Time to persist and publish one order"
)
PRICING_CALLS = Counter(
    "pricing_calls_total",
    "Outcomes of calls to the pricing service",
    ["result", "served_by"],
)

# The key pricing registers itself under with the health checking protocol is its
# fully-qualified proto service name. Read off the descriptor rather than written
# as a literal, so the two sides cannot drift when the .proto is renamed. An empty
# string would ask for the server's overall health; we want the one service we
# depend on. https://github.com/grpc/grpc/blob/master/doc/health-checking.md
PRICING_SERVICE_NAME = pricing_pb2.DESCRIPTOR.services_by_name["Pricing"].full_name

# The standard gRPC → HTTP status mapping. Collapsing every upstream failure to
# 502 tells the caller nothing: a deadline, an overload and a malformed order are
# three different problems with three different correct responses. Anything not
# listed is a genuine upstream fault, which is what 502 means.
GRPC_TO_HTTP_STATUS: dict[grpc.StatusCode, int] = {
    grpc.StatusCode.DEADLINE_EXCEEDED: 504,
    grpc.StatusCode.UNAVAILABLE: 503,
    grpc.StatusCode.INVALID_ARGUMENT: 400,
    grpc.StatusCode.RESOURCE_EXHAUSTED: 429,
}

# A server that answers Check with one of these is demonstrably reachable and
# responsive; it simply does not publish health for this service name. gRPC's own
# documentation requires clients to handle a server without the Health service,
# so this is "reachable, health unknown" — not a readiness failure.
HEALTH_NOT_PUBLISHED = (grpc.StatusCode.NOT_FOUND, grpc.StatusCode.UNIMPLEMENTED)


class PricingClient:
    """Thin async wrapper around the generated Pricing stub.

    Uses grpc.aio so a slow or unavailable pricing service can't block the
    event loop. Deliberately has no fallback path: a failed price is a failed
    order, not a locally guessed one.
    """

    def __init__(
        self, address: str, timeout_seconds: float, health_timeout_seconds: float
    ) -> None:
        self._channel = grpc.aio.insecure_channel(address)
        self._stub = pricing_pb2_grpc.PricingStub(self._channel)
        self._health_stub = health_pb2_grpc.HealthStub(self._channel)
        self._timeout_seconds = timeout_seconds
        self._health_timeout_seconds = health_timeout_seconds

    async def price_order(
        self, *, sku: str, quantity: int, unit_amount_cents: int, customer: str
    ) -> pricing_pb2.PriceOrderResponse:
        request = pricing_pb2.PriceOrderRequest(
            sku=sku,
            quantity=quantity,
            unit_amount_cents=unit_amount_cents,
            customer=customer,
        )
        return await self._stub.PriceOrder(request, timeout=self._timeout_seconds)

    async def is_ready(self) -> bool:
        """Ask pricing whether it is serving, over grpc.health.v1.

        This is a real RPC with a deadline, which is the only thing that proves
        the dependency is answering. Channel connectivity state does not: a
        channel that has never reached anything is IDLE or CONNECTING, both of
        which look fine and neither of which means a call would succeed.
        https://github.com/grpc/grpc/blob/master/doc/health-checking.md
        """
        request = health_pb2.HealthCheckRequest(service=PRICING_SERVICE_NAME)
        try:
            response = await self._health_stub.Check(
                request, timeout=self._health_timeout_seconds
            )
        except grpc.aio.AioRpcError as exc:
            if exc.code() in HEALTH_NOT_PUBLISHED:
                log.warning(
                    "pricing does not publish health for %s (code=%s); "
                    "treating a live response as ready",
                    PRICING_SERVICE_NAME,
                    exc.code(),
                )
                return True
            log.warning("pricing health check failed code=%s", exc.code())
            return False
        return response.status == health_pb2.HealthCheckResponse.SERVING

    async def close(self) -> None:
        await self._channel.close()


# ---------- state ----------
state: dict = {"producer": None, "s3": None, "pricing": None, "ready": False}


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Start dependencies before serving; drain them on shutdown."""
    state["s3"] = boto3.client(
        "s3",
        endpoint_url=settings.aws_endpoint_url,
        region_name=settings.aws_region,
        # Floci, like S3-compatible stores generally, needs path-style addressing.
        config=BotoConfig(s3={"addressing_style": "path"}, retries={"max_attempts": 3}),
    )
    producer = AIOKafkaProducer(
        bootstrap_servers=settings.kafka_brokers,
        acks="all",  # do not consider a write done until all ISRs have it
        enable_idempotence=True,  # no duplicates on internal retry
        linger_ms=5,
    )
    await producer.start()
    state["producer"] = producer
    state["pricing"] = PricingClient(
        settings.pricing_addr,
        settings.pricing_timeout_seconds,
        settings.pricing_health_timeout_seconds,
    )
    state["ready"] = True
    log.info("order-api started version=%s", settings.service_version)
    try:
        yield
    finally:
        state["ready"] = False
        await producer.stop()
        await state["pricing"].close()
        log.info("order-api stopped")


app = FastAPI(title="order-api", version=settings.service_version, lifespan=lifespan)

# prometheus_client ships an ASGI app for this; mounting it is what its docs
# prescribe. It negotiates content type and compression, and a mount is not a
# route, so /metrics stays out of the OpenAPI document Backstage renders.
# https://prometheus.github.io/client_python/exporting/http/fastapi-gunicorn/
app.mount("/metrics", make_asgi_app())


class OrderIn(BaseModel):
    customer: str = Field(min_length=1, max_length=128)
    sku: str = Field(min_length=1, max_length=64)
    quantity: int = Field(ge=1, le=1000)
    amount_cents: int = Field(ge=1)


@app.get("/healthz")
def healthz() -> dict:
    """Liveness: the process is running. Deliberately checks nothing else."""
    return {"status": "ok", "version": settings.service_version}


@app.get("/readyz")
async def readyz() -> dict:
    """Readiness: dependencies are up. Kubernetes pulls us out of the Service if this fails.

    Async because the pricing health check is a real RPC and must be awaited.
    """
    if not state["ready"]:
        raise HTTPException(status_code=503, detail="dependencies not ready")
    pricing = state["pricing"]
    if pricing is None or not await pricing.is_ready():
        raise HTTPException(status_code=503, detail="pricing not serving")
    return {"status": "ready"}


async def _price_order(order: OrderIn) -> pricing_pb2.PriceOrderResponse:
    """Call shop.v1.Pricing/PriceOrder. Any failure is an HTTPException carrying the
    gRPC status translated to its HTTP equivalent — never a locally computed price,
    so a pricing outage is a visible order failure rather than a silently wrong total."""
    pricing = state["pricing"]
    try:
        response = await pricing.price_order(
            sku=order.sku,
            quantity=order.quantity,
            unit_amount_cents=order.amount_cents,
            customer=order.customer,
        )
    except grpc.RpcError as exc:
        code = exc.code()
        result = "timeout" if code == grpc.StatusCode.DEADLINE_EXCEEDED else "error"
        PRICING_CALLS.labels(result=result, served_by="unknown").inc()
        log.warning("pricing call failed sku=%s code=%s", order.sku, code)
        raise HTTPException(
            status_code=GRPC_TO_HTTP_STATUS.get(code, 502),
            detail=f"pricing call failed: {code.name if code else 'UNKNOWN'}",
        ) from exc
    PRICING_CALLS.labels(result="ok", served_by=response.served_by).inc()
    return response


@app.post("/orders", status_code=202)
async def create_order(order: OrderIn) -> dict:
    started = time.perf_counter()
    order_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()

    try:
        pricing = await _price_order(order)

        payload = order.model_dump() | {
            "order_id": order_id,
            "created_at": created_at,
            "total_amount_cents": pricing.total_amount_cents,
            "priced_by": pricing.served_by,
        }
        body = json.dumps(payload, separators=(",", ":")).encode()

        # Sign the payload with a key that only ever exists in OpenBao.
        signature = hmac.new(
            settings.signing_key.encode(), body, hashlib.sha256
        ).hexdigest()

        key = f"orders/{created_at[:10]}/{order_id}.json"
        # boto3 is synchronous. Calling it directly from an `async def` path
        # operation blocks the event loop for the whole S3 round trip, which
        # stalls every other in-flight request and both probes with it. FastAPI's
        # answer for blocking I/O inside an async endpoint is to hand it to the
        # threadpool. https://fastapi.tiangolo.com/async/
        await run_in_threadpool(
            state["s3"].put_object,
            Bucket=settings.s3_bucket,
            Key=key,
            Body=body,
            ContentType="application/json",
            Metadata={"signature": signature},
        )
        event = payload | {"s3_key": key, "signature": signature}
        await state["producer"].send_and_wait(
            settings.kafka_topic,
            value=json.dumps(event, separators=(",", ":")).encode(),
            key=order_id.encode(),  # partition by order id → per-order ordering
        )
    except HTTPException:
        ORDERS_RECEIVED.labels(result="error").inc()
        raise
    except Exception:
        ORDERS_RECEIVED.labels(result="error").inc()
        log.exception("failed to ingest order_id=%s", order_id)
        raise HTTPException(status_code=502, detail="downstream failure")
    finally:
        ORDER_LATENCY.observe(time.perf_counter() - started)

    ORDERS_RECEIVED.labels(result="ok").inc()
    log.info("accepted order_id=%s key=%s", order_id, key)
    return {
        "order_id": order_id,
        "status": "accepted",
        "s3_key": key,
        "total_amount_cents": pricing.total_amount_cents,
        "discount_cents": pricing.discount_cents,
        "rule_applied": pricing.rule_applied,
        "priced_by": pricing.served_by,
    }


def main() -> None:
    """Entry point for the packaged pex_binary: run the ASGI app under uvicorn."""
    uvicorn.run(app, host="0.0.0.0", port=settings.order_api_port)


if __name__ == "__main__":
    main()
```

`grpcio-health-checking` ships no `py.typed` marker, so the ignore goes on the import rather than in a
global `ignore_missing_imports` — which would silence real typos in every other module too. `grpcio-health-checking` and `grpcio-reflection` are
already in `3rdparty/python/requirements.txt` ([§17.3](#173-pantstoml)) — they are first-party gRPC
add-ons shipped as separate packages, which is why they need naming at all.

```python
PRICING_CALLS = Counter(
    "pricing_calls_total",
    "Outcomes of calls to the pricing service",
    ["result", "served_by"],
)
```

`served_by` as a metric label is safe here only because its cardinality is bounded by the number of
deployed pricing versions. Do not label metrics with anything a caller controls.

Two module-level constants, because both are facts that must not be written twice:

```python
PRICING_SERVICE_NAME = pricing_pb2.DESCRIPTOR.services_by_name["Pricing"].full_name

GRPC_TO_HTTP_STATUS: dict[grpc.StatusCode, int] = {
    grpc.StatusCode.DEADLINE_EXCEEDED: 504,
    grpc.StatusCode.UNAVAILABLE: 503,
    grpc.StatusCode.INVALID_ARGUMENT: 400,
    grpc.StatusCode.RESOURCE_EXHAUSTED: 429,
}

HEALTH_NOT_PUBLISHED = (grpc.StatusCode.NOT_FOUND, grpc.StatusCode.UNIMPLEMENTED)
```

The service name is read off the descriptor for the same reason the server registers it that way — the
two sides cannot drift when the `.proto` is renamed. Collapsing every upstream status to 502 tells the
caller nothing: a deadline, an overload and a malformed order are three different problems with three
different correct responses, and only the unlisted ones are genuine upstream faults, which is what 502
means.

```python
class PricingClient:
    """Thin async wrapper around the generated Pricing stub.

    Uses grpc.aio so a slow or unavailable pricing service can't block the
    event loop. Deliberately has no fallback path: a failed price is a failed
    order, not a locally guessed one.
    """

    def __init__(
        self, address: str, timeout_seconds: float, health_timeout_seconds: float
    ) -> None:
        self._channel = grpc.aio.insecure_channel(address)
        self._stub = pricing_pb2_grpc.PricingStub(self._channel)
        self._health_stub = health_pb2_grpc.HealthStub(self._channel)
        self._timeout_seconds = timeout_seconds
        self._health_timeout_seconds = health_timeout_seconds

    async def price_order(
        self, *, sku: str, quantity: int, unit_amount_cents: int, customer: str
    ) -> pricing_pb2.PriceOrderResponse:
        request = pricing_pb2.PriceOrderRequest(
            sku=sku,
            quantity=quantity,
            unit_amount_cents=unit_amount_cents,
            customer=customer,
        )
        return await self._stub.PriceOrder(request, timeout=self._timeout_seconds)

    async def is_ready(self) -> bool:
        """Ask pricing whether it is serving, over grpc.health.v1.

        This is a real RPC with a deadline, which is the only thing that proves
        the dependency is answering. Channel connectivity state does not: a
        channel that has never reached anything is IDLE or CONNECTING, both of
        which look fine and neither of which means a call would succeed.
        https://github.com/grpc/grpc/blob/master/doc/health-checking.md
        """
        request = health_pb2.HealthCheckRequest(service=PRICING_SERVICE_NAME)
        try:
            response = await self._health_stub.Check(
                request, timeout=self._health_timeout_seconds
            )
        except grpc.aio.AioRpcError as exc:
            if exc.code() in HEALTH_NOT_PUBLISHED:
                return True
            log.warning("pricing health check failed code=%s", exc.code())
            return False
        return response.status == health_pb2.HealthCheckResponse.SERVING

    async def close(self) -> None:
        await self._channel.close()
```

**Readiness asks over `grpc.health.v1`; it does not read channel state.** `get_state()` reports what
the local channel object believes about its own connectivity, and a channel that has never reached
anything is `IDLE` or `CONNECTING` — both of which look fine, neither of which means a call would
succeed. A backend that does not exist at all reads as ready. `Check` is a real RPC: it either comes
back `SERVING` inside the deadline or it does not.

`NOT_FOUND` and `UNIMPLEMENTED` are treated as ready on purpose. gRPC's own documentation requires
clients to cope with a server that does not publish health, and a server that answered with a status
is by definition reachable — that is "health unknown", not "health failing".

`insecure_channel` is correct in this platform: the sidecar terminates mTLS, so TLS in the
application would be a second, redundant layer
([§9.4](phase-4-service-mesh.md#94-mtls-and-proving-it-is-actually-on)). The `timeout=` argument is the
deadline. Without it a synchronous hop turns a slow dependency into an outage — every request parks
on the event loop until the client gives up, and `order-api` stops answering for reasons that have
nothing to do with `order-api`.

**One channel per process, not per request.** Build it in the lifespan and drain it on shutdown, next
to Kafka and S3:

```python
state: dict = {"producer": None, "s3": None, "pricing": None, "ready": False}
```

```python
    state["pricing"] = PricingClient(
        settings.pricing_addr,
        settings.pricing_timeout_seconds,
        settings.pricing_health_timeout_seconds,
    )
    state["ready"] = True
    log.info("order-api started version=%s", settings.service_version)
    try:
        yield
    finally:
        state["ready"] = False
        await producer.stop()
        await state["pricing"].close()
        log.info("order-api stopped")
```

A gRPC channel is a long-lived, multiplexing object that manages its own connection pool and
reconnection. Creating one per request throws away the connection and pays a TCP and HTTP/2 handshake
on every order.

**Readiness gets a second condition.** If pricing is not serving, this pod cannot serve orders and
should be pulled out of the Service rather than answering errors:

```python
@app.get("/readyz")
async def readyz() -> dict:
    """Readiness: dependencies are up. Kubernetes pulls us out of the Service if this fails.

    Async because the pricing health check is a real RPC and must be awaited.
    """
    if not state["ready"]:
        raise HTTPException(status_code=503, detail="dependencies not ready")
    pricing = state["pricing"]
    if pricing is None or not await pricing.is_ready():
        raise HTTPException(status_code=503, detail="pricing not serving")
    return {"status": "ready"}
```

The handler is `async def` because `is_ready()` is now an awaited RPC. The health deadline is what
keeps that from being a liability: without one, a probe against a hung backend hangs with it, and the
kubelet's own probe timeout becomes the only thing that ends the request.

**The call.** One helper, so there is exactly one place that decides what a pricing failure means:

```python
async def _price_order(order: OrderIn) -> pricing_pb2.PriceOrderResponse:
    """Call shop.v1.Pricing/PriceOrder. Any failure is an HTTPException carrying the
    gRPC status translated to its HTTP equivalent — never a locally computed price,
    so a pricing outage is a visible order failure rather than a silently wrong total."""
    pricing = state["pricing"]
    try:
        response = await pricing.price_order(
            sku=order.sku,
            quantity=order.quantity,
            unit_amount_cents=order.amount_cents,
            customer=order.customer,
        )
    except grpc.RpcError as exc:
        code = exc.code()
        result = "timeout" if code == grpc.StatusCode.DEADLINE_EXCEEDED else "error"
        PRICING_CALLS.labels(result=result, served_by="unknown").inc()
        log.warning("pricing call failed sku=%s code=%s", order.sku, code)
        raise HTTPException(
            status_code=GRPC_TO_HTTP_STATUS.get(code, 502),
            detail=f"pricing call failed: {code.name if code else 'UNKNOWN'}",
        ) from exc
    PRICING_CALLS.labels(result="ok", served_by=response.served_by).inc()
    return response
```

`DEADLINE_EXCEEDED` is split out in the *metric* too, not just the status code, because "we were too
slow" and "it was broken" have different fixes and a single `result="error"` bucket hides which one you
have.

**In `create_order`**, price first, then persist. The price is part of the record, so an order that
cannot be priced must not reach S3 or Kafka at all:

```python
    try:
        pricing = await _price_order(order)

        payload = order.model_dump() | {
            "order_id": order_id,
            "created_at": created_at,
            "total_amount_cents": pricing.total_amount_cents,
            "priced_by": pricing.served_by,
        }
        body = json.dumps(payload, separators=(",", ":")).encode()
```

**The S3 write goes to the threadpool.** boto3 is synchronous, and a synchronous call inside an
`async def` path operation blocks the event loop for the whole round trip — every other in-flight
request and both probes stall with it. FastAPI's answer for blocking I/O inside an async endpoint is
`run_in_threadpool`:

```python
        await run_in_threadpool(
            state["s3"].put_object,
            Bucket=settings.s3_bucket,
            Key=key,
            Body=body,
            ContentType="application/json",
            Metadata={"signature": signature},
        )
```

This is the rule that decides whether a handler is `async def` at all: an `async def` endpoint may
only `await`. A handler that has blocking work and no threadpool should be a plain `def`, which
FastAPI then runs in the threadpool itself.

**`/metrics` is mounted, not routed.** `prometheus_client` ships an ASGI app for this and its docs
prescribe mounting it. It negotiates content type and compression, and a mount is not a route, so
`/metrics` stays out of the OpenAPI document Backstage renders
([§19.6](#196-two-checks-nothing-else-would-catch)):

```python
app.mount("/metrics", make_asgi_app())
```

The exception handling needs a clause it did not have before, and its order matters:

```python
    except HTTPException:
        ORDERS_RECEIVED.labels(result="error").inc()
        raise
    except Exception:
        ORDERS_RECEIVED.labels(result="error").inc()
        log.exception("failed to ingest order_id=%s", order_id)
        raise HTTPException(status_code=502, detail="downstream failure")
```

Without the first clause the bare `except Exception` swallows the `HTTPException` from `_price_order`
and re-raises a flat 502, throwing away the status the gRPC code was translated to and logging a stack
trace for a downstream failure that was already handled and counted.

Finally, the response carries the pricing result through:

```python
    return {
        "order_id": order_id,
        "status": "accepted",
        "s3_key": key,
        "total_amount_cents": pricing.total_amount_cents,
        "discount_cents": pricing.discount_cents,
        "rule_applied": pricing.rule_applied,
        "priced_by": pricing.served_by,
    }
```

**`priced_by` is the field [§19.4](#194-the-frontend-vite-and-a-live-tally) tallies.** The frontend
places orders against `order-api`, counts `priced_by` across the responses and draws the ratio. That is the entire
mechanism by which an Istio weight change becomes something you watch in a browser — it is `served_by`
off the wire ([§18.1](#181-the-contract)), renamed once on the way out and never aggregated in
between.

**Nothing to add to `services/order-api/BUILD`.** Pants resolves `from shop.v1 import pricing_pb2` to
the generated target from the import itself
([§17.1](#171-the-problem-with-a-build-tool-per-language)), and `grpcio` is already in
`3rdparty/python/requirements.txt`. Confirm rather than assume:

```bash
pants dependencies --transitive services/order-api:bin | grep protos
# protos/shop/v1/pricing.proto:protos
```

**The tests.** Fakes, so the suite never opens a socket:

**`services/order-api/tests/test_api.py`**

```python
import asyncio
import os
import threading

# Settings are read at import time, so the environment must be set first.
os.environ.setdefault("KAFKA_BROKERS", "localhost:9092")
os.environ.setdefault("S3_BUCKET", "test-bucket")
os.environ.setdefault("ORDER_SIGNING_KEY", "test-key")

import grpc  # noqa: E402
import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from grpc_health.v1 import health_pb2  # type: ignore[import-untyped]  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from order_api.main import (  # noqa: E402
    OrderIn,
    PricingClient,
    app,
    create_order,
    healthz,
    readyz,
    state,
)
from shop.v1 import pricing_pb2  # noqa: E402


class _FakeS3:
    """Records the thread `put_object` ran on, because that is the thing under test."""

    def __init__(self) -> None:
        self.thread_name: str | None = None

    def put_object(self, **kwargs):
        self.thread_name = threading.current_thread().name


class _FakeProducer:
    async def send_and_wait(self, *args, **kwargs):
        pass


class _FakePricingClient:
    """Stands in for PricingClient so tests never touch the network."""

    def __init__(
        self, *, response=None, error: grpc.RpcError | None = None, ready=True
    ):
        self._response = response
        self._error = error
        self._ready = ready

    async def price_order(self, **kwargs):
        if self._error is not None:
            raise self._error
        return self._response

    async def is_ready(self) -> bool:
        return self._ready


class _FakeRpcError(grpc.RpcError):
    def __init__(self, code: grpc.StatusCode):
        self._code = code

    def code(self) -> grpc.StatusCode:
        return self._code


class _FakeHealthStub:
    """Answers grpc.health.v1 Check the way a real server would."""

    def __init__(self, *, status=None, error: grpc.aio.AioRpcError | None = None):
        self._status = status
        self._error = error

    async def Check(self, request, timeout=None):  # noqa: N802  (gRPC method name)
        assert request.service == "shop.v1.Pricing"
        if self._error is not None:
            raise self._error
        return health_pb2.HealthCheckResponse(status=self._status)


def _aio_rpc_error(code: grpc.StatusCode) -> grpc.aio.AioRpcError:
    return grpc.aio.AioRpcError(code, grpc.aio.Metadata(), grpc.aio.Metadata())


def _order() -> OrderIn:
    return OrderIn(customer="ada", sku="W-1", quantity=3, amount_cents=4999)


def _priced_state() -> _FakeS3:
    s3 = _FakeS3()
    state["s3"] = s3
    state["producer"] = _FakeProducer()
    return s3


async def _health_result(**stub_kwargs) -> bool:
    client = PricingClient(
        "localhost:1", timeout_seconds=1.0, health_timeout_seconds=1.0
    )
    client._health_stub = _FakeHealthStub(**stub_kwargs)
    try:
        return await client.is_ready()
    finally:
        await client.close()


def test_healthz_needs_no_dependencies():
    """Liveness must answer without Kafka or S3, or a broker outage kills every pod."""
    assert healthz()["status"] == "ok"


def test_readyz_is_not_ready_before_startup():
    assert state["ready"] is False


@pytest.mark.parametrize(
    "field,value",
    [("quantity", 0), ("quantity", 1001), ("amount_cents", 0), ("customer", "")],
)
def test_invalid_orders_are_rejected(field, value):
    payload = {"customer": "ada", "sku": "W-1", "quantity": 1, "amount_cents": 100}
    payload[field] = value
    with pytest.raises(ValidationError):
        OrderIn(**payload)


def test_valid_order_is_accepted():
    order = OrderIn(customer="ada", sku="W-1", quantity=3, amount_cents=4999)
    assert order.quantity == 3


def test_routes_are_registered():
    paths = {r.path for r in app.routes}
    assert {"/orders", "/healthz", "/readyz", "/metrics"} <= paths


def test_metrics_is_mounted_not_a_route():
    """prometheus_client's ASGI app is mounted, which keeps /metrics out of the
    OpenAPI document. A hand-rolled route would put it back in."""
    assert "/metrics" not in app.openapi()["paths"]


def test_order_response_includes_pricing_result():
    _priced_state()
    state["pricing"] = _FakePricingClient(
        response=pricing_pb2.PriceOrderResponse(
            total_amount_cents=4499,
            discount_cents=500,
            rule_applied="volume-discount",
            served_by="pricing-v1",
        )
    )

    result = asyncio.run(create_order(_order()))

    assert result["status"] == "accepted"
    assert result["total_amount_cents"] == 4499
    assert result["discount_cents"] == 500
    assert result["rule_applied"] == "volume-discount"
    assert result["priced_by"] == "pricing-v1"


def test_s3_put_does_not_run_on_the_event_loop_thread():
    """boto3 is synchronous. Called directly from this `async def` endpoint it
    would stall the loop — and every other request with it — for the whole S3
    round trip, so it has to go to the threadpool."""
    s3 = _priced_state()
    state["pricing"] = _FakePricingClient(
        response=pricing_pb2.PriceOrderResponse(total_amount_cents=1)
    )

    asyncio.run(create_order(_order()))

    assert s3.thread_name is not None
    assert s3.thread_name != threading.current_thread().name


@pytest.mark.parametrize(
    "code,expected_status",
    [
        (grpc.StatusCode.DEADLINE_EXCEEDED, 504),
        (grpc.StatusCode.UNAVAILABLE, 503),
        (grpc.StatusCode.INVALID_ARGUMENT, 400),
        (grpc.StatusCode.RESOURCE_EXHAUSTED, 429),
        (grpc.StatusCode.INTERNAL, 502),
        (grpc.StatusCode.UNKNOWN, 502),
    ],
)
def test_pricing_failures_map_to_their_http_equivalent(code, expected_status):
    """One gRPC status, one HTTP status. Collapsing them all to 502 tells the
    caller a timeout, an overload and a malformed order are the same thing."""
    _priced_state()
    state["pricing"] = _FakePricingClient(error=_FakeRpcError(code))

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(create_order(_order()))

    assert exc_info.value.status_code == expected_status


def test_readyz_fails_when_pricing_is_not_serving():
    state["ready"] = True
    state["pricing"] = _FakePricingClient(ready=False)
    try:
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(readyz())
    finally:
        state["ready"] = False

    assert exc_info.value.status_code == 503


def test_readyz_passes_when_pricing_is_serving():
    state["ready"] = True
    state["pricing"] = _FakePricingClient(ready=True)
    try:
        assert asyncio.run(readyz()) == {"status": "ready"}
    finally:
        state["ready"] = False


def test_health_check_serving_is_ready():
    assert (
        asyncio.run(_health_result(status=health_pb2.HealthCheckResponse.SERVING))
        is True
    )


@pytest.mark.parametrize(
    "status",
    [
        health_pb2.HealthCheckResponse.NOT_SERVING,
        health_pb2.HealthCheckResponse.SERVICE_UNKNOWN,
        health_pb2.HealthCheckResponse.UNKNOWN,
    ],
)
def test_health_check_not_serving_is_not_ready(status):
    """Only SERVING means ready. Channel connectivity would report every one of
    these as fine, which is why readiness asks over grpc.health.v1 instead."""
    assert asyncio.run(_health_result(status=status)) is False


def test_unreachable_pricing_is_not_ready():
    """A pricing backend that has never existed must not report ready."""
    assert (
        asyncio.run(_health_result(error=_aio_rpc_error(grpc.StatusCode.UNAVAILABLE)))
        is False
    )


@pytest.mark.parametrize(
    "code", [grpc.StatusCode.NOT_FOUND, grpc.StatusCode.UNIMPLEMENTED]
)
def test_server_without_the_health_service_is_still_ready(code):
    """gRPC's docs require clients to handle a server that does not publish
    health. It answered, so it is reachable — health is unknown, not failing."""
    assert asyncio.run(_health_result(error=_aio_rpc_error(code))) is True
```

`grpc.RpcError` is a bare `Exception` subclass with no constructor of its own, so a real one cannot be
raised with a chosen status code — `_FakeRpcError` exists only to make `code()` answer. `_FakeHealthStub`
is substituted onto a real `PricingClient`, so `is_ready()` runs its actual branching over every
health status and every error code.

The happy path asserts the response actually carries the price through:

```python
def test_order_response_includes_pricing_result():
    _priced_state()
    state["pricing"] = _FakePricingClient(
        response=pricing_pb2.PriceOrderResponse(
            total_amount_cents=4499,
            discount_cents=500,
            rule_applied="volume-discount",
            served_by="pricing-v1",
        )
    )

    result = asyncio.run(create_order(_order()))

    assert result["status"] == "accepted"
    assert result["total_amount_cents"] == 4499
    assert result["discount_cents"] == 500
    assert result["rule_applied"] == "volume-discount"
    assert result["priced_by"] == "pricing-v1"
```

The status mapping gets one parametrised test, so adding a status to the table without a case here is
visible:

```python
@pytest.mark.parametrize(
    "code,expected_status",
    [
        (grpc.StatusCode.DEADLINE_EXCEEDED, 504),
        (grpc.StatusCode.UNAVAILABLE, 503),
        (grpc.StatusCode.INVALID_ARGUMENT, 400),
        (grpc.StatusCode.RESOURCE_EXHAUSTED, 429),
        (grpc.StatusCode.INTERNAL, 502),
        (grpc.StatusCode.UNKNOWN, 502),
    ],
)
def test_pricing_failures_map_to_their_http_equivalent(code, expected_status):
    """One gRPC status, one HTTP status. Collapsing them all to 502 tells the
    caller a timeout, an overload and a malformed order are the same thing."""
    _priced_state()
    state["pricing"] = _FakePricingClient(error=_FakeRpcError(code))

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(create_order(_order()))

    assert exc_info.value.status_code == expected_status
```

These are the tests that keep the no-fallback decision from being quietly reversed later. A fallback
would have to change every expected status here, which is the point.

Two more assert things that are otherwise invisible. The first catches a blocking call sneaking back
onto the event loop; it works because `_FakeS3` records the thread it ran on:

```python
def test_s3_put_does_not_run_on_the_event_loop_thread():
    """boto3 is synchronous. Called directly from this `async def` endpoint it
    would stall the loop — and every other request with it — for the whole S3
    round trip, so it has to go to the threadpool."""
    s3 = _priced_state()
    state["pricing"] = _FakePricingClient(
        response=pricing_pb2.PriceOrderResponse(total_amount_cents=1)
    )

    asyncio.run(create_order(_order()))

    assert s3.thread_name is not None
    assert s3.thread_name != threading.current_thread().name
```

The second pins readiness to the health protocol rather than to channel state — a backend that has
never existed must not read as ready:

```python
@pytest.mark.parametrize(
    "status",
    [
        health_pb2.HealthCheckResponse.NOT_SERVING,
        health_pb2.HealthCheckResponse.SERVICE_UNKNOWN,
        health_pb2.HealthCheckResponse.UNKNOWN,
    ],
)
def test_health_check_not_serving_is_not_ready(status):
    """Only SERVING means ready. Channel connectivity would report every one of
    these as fine, which is why readiness asks over grpc.health.v1 instead."""
    assert asyncio.run(_health_result(status=status)) is False
```

`services/pricing/tests/test_pricing.py` takes the other side of both protocols the same way: it builds
the real server with `build_server()`, binds `[::]:0`, and drives health checking, reflection and
`PriceOrder` over a real channel. Health and reflection are wire protocols; an in-process assertion
would prove nothing about what a kubelet or `grpcurl` sees.

```bash
pants test services/order-api:tests
```

Once the images are built and Argo CD has synced, the call is visible end to end:

```bash
curl -s -X POST http://shop.localtest.me/orders \
  -H 'content-type: application/json' \
  -d '{"customer":"ada","sku":"W-1","quantity":3,"amount_cents":4999}' | jq .
```

A `priced_by` of `pricing-v1` or `pricing-v2` in that response means the hop works. Repeat it and
watch which version answers — that is the canary, in one command, before the frontend exists.

### 19.2 `pex_binary`, and the one flag that decides whether it runs

A PEX is a single executable zip containing your code and its entire dependency closure. `python
order-api.pex` runs it; there is no `pip install` step at any point after Pants.

First, describe the platform the PEX will actually run on. Generate it from a real container rather
than writing it by hand:

```bash
docker run --rm python:3.13-slim sh -c \
  'pip install pex && pex3 interpreter inspect --markers --tags' > 3rdparty/python/linux.json
```

**`3rdparty/python/BUILD`**

```python
python_requirements(
    name="reqs",
    source="requirements.txt",
)

# The cluster's real platform: linux/aarch64, CPython 3.13. Generated with
#   docker run --rm python:3.13-slim sh -c 'pip install pex && pex3 interpreter inspect --markers --tags'
#
# Every pex_binary MUST reference this via `complete_platforms`. Without it,
# `pants package` on a macOS laptop resolves macOS wheels — grpcio, pydantic
# core, uvloop and watchfiles are all native — and produces a PEX that builds
# cleanly, passes every check, and then dies on import inside a linux
# container. The failure is at runtime, in the cluster, far from the cause.
file(
    name="linux-platform",
    source="linux.json",
)
```

**`services/pricing/BUILD`**

```python
python_sources(
    name="lib",
    sources=["pricing/**/*.py"],
    # Dependency inference resolves the `shop.v1.pricing_pb2*` imports back to the
    # protobuf_sources target, but it's declared explicitly here too since it's
    # cross-source-root (protos/ vs services/pricing/) and easy to miss on inference
    # cache invalidation.
    dependencies=["protos/shop/v1:protos"],
)

python_sources(
    name="tests_pkg",
    sources=["tests/__init__.py"],
)

python_tests(
    name="tests",
    sources=["tests/test_*.py"],
    # The `app` top-level package name collides with order-api's own `app` package
    # under the shared `/services/*` source root, so dependency inference can't
    # disambiguate `from pricing.main import ...` on its own.
    dependencies=[":lib"],
)

pex_binary(
    name="bin",
    tags=["deployable"],
    entry_point="pricing/main.py:main",
    dependencies=[":lib"],
    # The cluster runs linux/aarch64 CPython 3.13, not this macOS laptop. grpcio
    # is a native extension; without this, `pants package` resolves macOS wheels
    # that build and pass every check here, then fail to import in the cluster.
    complete_platforms=["3rdparty/python:linux-platform"],
    # Land in dist/ under a predictable name so dist/ can be used
    # directly as the Buildah build context and the Dockerfile can COPY by
    # name. Default would be dist/services.<name>/bin.pex.
    output_path="pricing.pex",
)
```

`tags=["deployable"]` is what CI selects on ([§19.5](#195-one-ci-step-instead-of-two)). Every target
that ships an artifact declares it — `services/order-api:bin`, `services/order-worker:bin`, and the one
the Backstage skeleton emits.

`complete_platforms` goes on **every** `pex_binary` in the repo, including the one the Backstage
skeleton emits. The cluster is `linux/aarch64`; the laptop is not, and `grpcio`, `pydantic-core`,
`uvloop` and `watchfiles` are all native extensions — without it `pants package` resolves macOS wheels
into an artifact that builds, tests and pushes cleanly and then fails to import inside the container.
Check the result:

```bash
unzip -l dist/pricing.pex | grep -E 'manylinux|macosx' | head
```

You want `manylinux2014_aarch64` in the wheel filenames, not `macosx`.

`output_path` exists so the artifact lands at `dist/pricing.pex` rather than the default
`dist/services.pricing/bin.pex`, which is what lets `dist/` be used directly as a Buildah build
context and the Dockerfile `COPY` by name.

> **One constraint follows from cross-packaging.** Every platform-specific dependency must be
> available as a **prebuilt wheel** for the target — Pants can only build sdists for the local
> machine. A dependency that ships source-only for `linux/aarch64` cannot be cross-packaged at all;
> you would have to build the wheel yourself and host it in Nexus. This is not a Pants
> quirk. Any tool that resolves wheels on the build host and ships them elsewhere has it, and it is
> the same class of mistake as building a Go binary with `CGO_ENABLED=1` and putting it in `scratch`.

The Dockerfile that consumes it is the whole payoff:

```dockerfile
# syntax=docker/dockerfile:1.7
FROM docker.io/library/python:3.13-slim

RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin appuser

WORKDIR /app
COPY --chown=10001:10001 pricing.pex /app/pricing.pex

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER 10001
# 50051 gRPC (application, health checking and reflection), 9090 Prometheus
# metrics. Probes speak the gRPC health protocol on 50051, not HTTP.
EXPOSE 50051 9090
ENTRYPOINT ["python", "/app/pricing.pex"]
```

No `uv sync`, no layer-caching strategy, no index configuration, no build-time network access at all.
Compare it to [§3.1](phase-1-the-application.md#31-order-api-python--fastapi)'s multi-stage Dockerfile and the
argument makes itself.

### 19.3 A PEX needs somewhere to write, and `readOnlyRootFilesystem` gives it nowhere

A PEX is a zip that **unpacks its dependency closure on first run**. The bootstrap extracts wheels to
`PEX_ROOT`, which must be writable, and falls back to the temp directory when it is not — so under
`readOnlyRootFilesystem: true` every candidate fails and the process dies before importing a line of
your code. None of your logging configuration has run at that point, so `kubectl logs` shows nothing
at all.

Give it a writable `/tmp` and point `PEX_ROOT` at it explicitly, keeping the root filesystem
read-only. The volume half, from `deploy/charts/order-platform/templates/pricing.yaml`:

```yaml
          envFrom:
            - configMapRef: { name: pricing-config }
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities: { drop: ["ALL"] }
          volumeMounts:
            - { name: tmp, mountPath: /tmp }
      volumes:
        - { name: tmp, emptyDir: {} }
```

**`deploy/charts/order-platform/templates/configmap-pricing.yaml`**

```yaml
{{- if .Values.pricing.enabled }}
{{/*
v1 and v2 share one ConfigMap because they share one config; what differs
between them — PRICING_VERSION and the image tag — stays inline on each
Deployment, where it belongs to the pod template rather than to the config.
*/}}
apiVersion: v1
kind: ConfigMap
metadata:
  name: pricing-config
  labels: {{- include "op.labels" (dict "name" "pricing" "root" $) | nindent 4 }}
data:
  PRICING_GRPC_PORT: {{ .Values.pricing.grpcPort | quote }}
  PRICING_HTTP_PORT: {{ .Values.pricing.httpPort | quote }}
  # PEX unpacks its dependency closure here; see the /tmp volumeMount note on the
  # Deployment.
  PEX_ROOT: "/tmp/pex"
{{- end }}
```

The variable half lives in `configmap-pricing.yaml`, the file that Deployment's `checksum/config`
annotation hashes:

```yaml
data:
  PRICING_GRPC_PORT: {{ .Values.pricing.grpcPort | quote }}
  PRICING_HTTP_PORT: {{ .Values.pricing.httpPort | quote }}
  PEX_ROOT: "/tmp/pex"
```

A ConfigMap rather than inline `env`, because that is what makes the restart annotation on the
Deployment mean something:

```yaml
        checksum/config: {{ include (print $.Template.BasePath "/configmap-pricing.yaml") $ | sha256sum }}
```

That is Helm's documented form, and the file it names is this service's ConfigMap and nothing else.
Hash `.Values` instead and every deploy restarts every pod in the namespace, because CI rewrites the
image tags in the env overlay on every build. v1 and v2 share the ConfigMap because they share the
config; what differs between them — `PRICING_VERSION` and the image tag — stays inline on each
Deployment, where it belongs to the pod template rather than to the config.

Set `PEX_ROOT` rather than relying on `/tmp` being writable by default — the fallback order is an
implementation detail, and an explicit path is a thing a reader can find. **Every service packaged as
a PEX needs both halves.** `order-api` and `pricing` take `PEX_ROOT` from their ConfigMaps; a
scaffolded service takes it from an `ENV` in the skeleton's Dockerfile. All three Deployments carry
the `/tmp` emptyDir, so a service that arrives through the paved path gets them without anyone
remembering to ask.

**The probes are gRPC, not HTTP.** The kubelet speaks the health checking protocol itself, so the app
needs no HTTP endpoint for probes and the image needs no `grpc_health_probe` binary:

```yaml
          livenessProbe:
            grpc: { port: 50051 }
            periodSeconds: 10
            failureThreshold: 3
          readinessProbe:
            grpc: { port: 50051, service: shop.v1.Pricing }
            periodSeconds: 5
            failureThreshold: 2
```

Liveness asks for the empty service name — the server's overall health, which is what a `grpc:` probe
with no `service:` field requests. Readiness names `shop.v1.Pricing`, the one service that has to work
for this pod to be worth routing to. `GRPCAction.port` is an `int32`, not an `IntOrString`, so a port
*name* is rejected by the API server; it must be the number.

One more line in that file is not cosmetic: the metrics port is named **`http-metrics`**, not
`metrics`. Istio reads the protocol off the port name (`protocol[-suffix]`) or off `appProtocol`. A
port named `metrics` matches no protocol, Istio falls back to plain TCP, and `istioctl analyze`
reports `IST0118`.

Both Deployments come out of one `range` over `v1` and `v2`, and both are offered a
PodDisruptionBudget — but only `pricing-v1` gets one. The `op.pdb` helper renders nothing below two
replicas, because `minAvailable: 1` against a single replica permits zero voluntary evictions and
blocks a node drain forever. `pricing-v2` runs one replica, so draining its node is allowed to take
it out; that is the correct answer for a canary at one replica, and the reason the helper takes the
replica count rather than assuming it.

It is the same class of problem as `nginx-unprivileged` needing writable `/tmp`, `/var/cache/nginx`
and `/var/run`: both render perfectly under `helm template`, pass `kubectl apply --dry-run=server`,
and fail only at runtime. **Dry-run validates schema, not whether the process can start.**

```bash
kubectl -n shop get pods -l app.kubernetes.io/name=pricing
# pricing-v1-... 2/2 Running     (2/2 — the sidecar is the second container)
# pricing-v2-... 2/2 Running
```

### 19.4 The frontend: Vite, and a live tally

`frontend/` is a Vite + TypeScript page with no framework. It POSTs orders to `order-api`,
tallies the `priced_by` on each response, and draws a bar. A 90/10 → 50/50 weight change is visible in a
browser within seconds.

It is a demo dashboard, and it earns its place for one reason: **it makes the canary a thing you watch
rather than a thing you query.** The same information is in Prometheus. Nobody stands at a Prometheus
console watching a ratio move.

The app itself. A Vite + TypeScript page with no framework, and a pure function in its own
module so there is something worth unit-testing:

**`frontend/package.json`**

```json
{
  "name": "shop-canary-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "engines": {
    "node": ">=22.12.0"
  },
  "scripts": {
    "dev": "vite",
    "build": "tsc --noEmit && vite build",
    "preview": "vite preview",
    "test": "node --test src/*.test.ts"
  },
  "devDependencies": {
    "typescript": "7.0.2",
    "vite": "8.2.1",
    "@types/node": "26.2.0"
  }
}
```

**`frontend/.npmrc`**

```ini
registry=http://nexus:8081/repository/npm-proxy/
```

> **`.npmrc` points npm at Nexus for the same reason everything else does** — the frontend's
> dependencies are supply-chain events too ([§5.1](phase-0-foundations.md#51-what-nexus-is-actually-for)).

**`frontend/tsconfig.json`**

```json
{
  "compilerOptions": {
    // Required by Pants\' TypeScript backend, which refuses to typecheck
    // without an explicit outDir. vite ignores it — it writes to its own
    // build.outDir — so this exists purely so `pants check` can run.
    "outDir": "./dist",
    "target": "ES2022",
    "useDefineForClassFields": true,
    "module": "ESNext",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "skipLibCheck": true,

    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "isolatedModules": true,
    "moduleDetection": "force",
    "noEmit": true,

    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,

    "types": ["vite/client", "node"]
  },
  "include": ["src"]
}
```

**`frontend/vite.config.ts`**

```ts
import { defineConfig } from "vite";

export default defineConfig({
  build: {
    outDir: "dist",
  },
});
```

**`frontend/index.html`**

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Canary Watch — pricing v1/v2</title>
    <link rel="stylesheet" href="/src/style.css" />
  </head>
  <body>
    <div id="app"></div>
    <script type="module" src="/src/main.ts"></script>
  </body>
</html>
```

**`frontend/src/tally.ts`**

```ts
// Pure, DOM-free tally logic — kept separate from main.ts so it can be unit
// tested directly (see tally.test.ts) without a browser.
//
// The whole point of this module: `priced_by` is a free-form string on the
// wire, not a closed v1/v2 union (see api.ts). Tallying must key on
// whatever string actually came back, so an unexpected value shows up as
// its own bucket instead of being folded into an existing one.

const PALETTE = ["#4f8cff", "#ff9f43", "#2ecc71", "#e84393", "#a29bfe", "#00cec9"];

/**
 * Records one occurrence of `key` in `counts`, in place. `key` is whatever
 * `priced_by` the backend returned — no validation, no fallback bucket.
 */
export function recordPriced(counts: Map<string, number>, key: string): void {
  counts.set(key, (counts.get(key) ?? 0) + 1);
}

/** Total occurrences across all keys. */
export function totalOf(counts: Map<string, number>): number {
  let sum = 0;
  for (const n of counts.values()) sum += n;
  return sum;
}

/** Percentage (0-100, rounded) of `key` within `counts`. 0 if the total is 0. */
export function percentOf(counts: Map<string, number>, key: string): number {
  const total = totalOf(counts);
  if (total === 0) return 0;
  return Math.round(((counts.get(key) ?? 0) / total) * 100);
}

/**
 * Stable colour per key, assigned from a small palette in first-seen order
 * and cached in `assigned` so a key never changes colour across renders,
 * even as new keys appear or the bar re-sorts.
 */
export function colorFor(key: string, assigned: Map<string, string>): string {
  const existing = assigned.get(key);
  if (existing) return existing;
  const color = PALETTE[assigned.size % PALETTE.length] as string;
  assigned.set(key, color);
  return color;
}
```

**`frontend/src/tally.test.ts`**

```ts
// Exercises the tally logic in isolation from the DOM. Uses Node's built-in
// test runner and assert module — no new dependencies, matches the "no new
// deps" constraint on this frontend.
//
// Run with: node --test src/tally.test.ts

import { test } from "node:test";
import assert from "node:assert/strict";
import { recordPriced, totalOf, percentOf, colorFor } from "./tally.ts";

test("known values (v1/v2) split as expected", () => {
  const counts = new Map<string, number>();
  recordPriced(counts, "v1");
  recordPriced(counts, "v1");
  recordPriced(counts, "v1");
  recordPriced(counts, "v2");

  assert.equal(counts.get("v1"), 3);
  assert.equal(counts.get("v2"), 1);
  assert.equal(totalOf(counts), 4);
  assert.equal(percentOf(counts, "v1"), 75);
  assert.equal(percentOf(counts, "v2"), 25);
});

test("an unexpected priced_by value gets its own bucket, not folded into an existing one", () => {
  const counts = new Map<string, number>();
  recordPriced(counts, "v1");
  recordPriced(counts, "v1");
  recordPriced(counts, "pricing-v1"); // e.g. served_by from a different service naming scheme

  // The old bug: anything !== "v1" was counted as v2. Prove that no longer
  // happens — "pricing-v1" must NOT be added to "v1"'s count, and must NOT
  // silently create/inflate a "v2" bucket that was never actually seen.
  assert.equal(counts.get("v1"), 2);
  assert.equal(counts.get("pricing-v1"), 1);
  assert.equal(counts.has("v2"), false);
  assert.equal(counts.size, 2);
  assert.equal(totalOf(counts), 3);
});

test("three distinct versions each get their own bucket", () => {
  const counts = new Map<string, number>();
  recordPriced(counts, "v1");
  recordPriced(counts, "v2");
  recordPriced(counts, "v3-canary");

  assert.equal(counts.size, 3);
  assert.equal(percentOf(counts, "v1"), 33);
  assert.equal(percentOf(counts, "v2"), 33);
  assert.equal(percentOf(counts, "v3-canary"), 33);
});

test("colorFor is stable per key and does not reassign on repeated calls", () => {
  const assigned = new Map<string, string>();
  const first = colorFor("v1", assigned);
  const second = colorFor("v2", assigned);
  const firstAgain = colorFor("v1", assigned);

  assert.equal(firstAgain, first);
  assert.notEqual(first, second);
});

test("empty counts: total and percent are 0, not NaN or a divide-by-zero error", () => {
  const counts = new Map<string, number>();
  assert.equal(totalOf(counts), 0);
  assert.equal(percentOf(counts, "v1"), 0);
});
```

**`frontend/src/api.ts`**

```ts
// Talks to POST /orders on the order-api service. Base URL is configurable so
// local dev (vite dev server, different origin) can point at a reachable
// host, while the in-cluster build defaults to "" (same-origin, proxied by
// nginx — see frontend/nginx.conf) and needs no CORS handling at all.
const API_BASE = import.meta.env.VITE_API_BASE ?? "";

export interface OrderRequest {
  customer: string;
  sku: string;
  quantity: number;
  amount_cents: number;
}

export interface OrderResponse {
  order_id: string;
  status: string;
  s3_key: string;
  total_amount_cents: number;
  discount_cents: number;
  // Both are free-form strings on the wire (shop.v1.PriceOrderResponse) —
  // nothing on this side enforces a two-value union, and treating them as
  // one is what let an unrecognized value get silently folded into "v2" in
  // the tally. Display them as whatever the backend actually sent.
  rule_applied: string;
  priced_by: string;
}

export class OrderApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "OrderApiError";
  }
}

export async function placeOrder(req: OrderRequest): Promise<OrderResponse> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/orders`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(req),
    });
  } catch (err) {
    // Network failure (service unreachable, DNS, etc) — no HTTP status at all.
    throw new OrderApiError(
      err instanceof Error ? err.message : "network error",
      0,
    );
  }

  if (!res.ok) {
    throw new OrderApiError(`order-api returned ${res.status}`, res.status);
  }

  return (await res.json()) as OrderResponse;
}
```

**`frontend/src/main.ts`**

```ts
import { placeOrder, OrderApiError, type OrderResponse } from "./api";
import { recordPriced, totalOf, percentOf, colorFor } from "./tally";

interface LogEntry {
  quantity: number;
  totalCents: number | null;
  ruleApplied: string;
  pricedBy: string;
  ok: boolean;
  // The HTTP status the request actually failed with, or 0 when the request
  // never reached order-api. Not every failure is a 502: order-api maps a
  // pricing deadline to 504, an unavailable pricing to 503, a rejected order
  // to 400 and throttling to 429, and showing the real one is the difference
  // between "the canary is broken" and "the canary is slow".
  status: number;
}

interface State {
  counts: Map<string, number>;
  errors: number;
  log: LogEntry[];
}

const MAX_LOG = 20;
const CONTINUOUS_INTERVAL_MS = 500; // 2/sec

const state: State = { counts: new Map(), errors: 0, log: [] };
// Colour assignment persists independently of `state` so a version keeps its
// colour across a render even if it briefly has zero share; reset explicitly
// clears it alongside the counts so a fresh session reassigns from scratch.
let colors = new Map<string, string>();

let continuousTimer: ReturnType<typeof setInterval> | null = null;

const app = document.querySelector<HTMLDivElement>("#app");
if (!app) {
  throw new Error("#app element not found");
}

app.innerHTML = `
  <main>
    <header>
      <h1>Canary Watch</h1>
      <p class="subtitle">Live split of <code>pricing</code> versions, by order.</p>
    </header>

    <section class="tally" aria-label="live version split">
      <div class="tally-bar" id="tally-bar"></div>
      <div class="tally-labels" id="tally-labels"></div>
      <div class="tally-meta">
        <span id="version-count-label"></span>
        <span class="tally-label errors"><strong id="err-count">0</strong> failed</span>
      </div>
    </section>

    <section class="controls">
      <div class="field">
        <label for="quantity">Quantity</label>
        <input type="number" id="quantity" min="1" step="1" value="1" />
      </div>
      <div class="field">
        <label for="amount">Unit amount ($)</label>
        <input type="number" id="amount" min="0" step="0.01" value="19.99" />
      </div>
      <div class="buttons">
        <button id="send-one" type="button">Send order</button>
        <button id="send-twenty" type="button">Send 20 orders</button>
        <button id="toggle-continuous" type="button">Start continuous (2/sec)</button>
        <button id="reset" type="button" class="secondary">Reset counters</button>
      </div>
      <p class="hint">Quantity &ge; 3 crosses the bulk-discount boundary that triggers v2's <code>bulk-10pct</code> rule.</p>
    </section>

    <section class="log-section">
      <h2>Last ${MAX_LOG} orders</h2>
      <table class="log">
        <thead>
          <tr>
            <th>#</th>
            <th>qty</th>
            <th>total</th>
            <th>rule</th>
            <th>priced by</th>
          </tr>
        </thead>
        <tbody id="log-body"></tbody>
      </table>
    </section>
  </main>
`;

const el = <T extends HTMLElement>(id: string): T => {
  const found = document.getElementById(id);
  if (!found) throw new Error(`missing #${id}`);
  return found as T;
};

const quantityInput = el<HTMLInputElement>("quantity");
const amountInput = el<HTMLInputElement>("amount");
const sendOneBtn = el<HTMLButtonElement>("send-one");
const sendTwentyBtn = el<HTMLButtonElement>("send-twenty");
const toggleContinuousBtn = el<HTMLButtonElement>("toggle-continuous");
const resetBtn = el<HTMLButtonElement>("reset");

const tallyBar = el<HTMLDivElement>("tally-bar");
const tallyLabels = el<HTMLDivElement>("tally-labels");
const versionCountLabel = el<HTMLElement>("version-count-label");
const errCountEl = el<HTMLElement>("err-count");
const logBody = el<HTMLTableSectionElement>("log-body");

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function render(): void {
  const total = totalOf(state.counts);
  const keys = [...state.counts.keys()];

  // One bar segment + one label per distinct version actually seen. An
  // unexpected priced_by value gets its own segment, not a fold into v2.
  tallyBar.innerHTML = keys
    .map((key) => {
      const pct = total === 0 ? 0 : percentOf(state.counts, key);
      const width = total === 0 ? 100 / Math.max(keys.length, 1) : pct;
      return `<div class="tally-segment" style="width:${width}%;background:${colorFor(key, colors)}"></div>`;
    })
    .join("");

  tallyLabels.innerHTML = keys
    .map((key) => {
      const pct = percentOf(state.counts, key);
      const count = state.counts.get(key) ?? 0;
      return `<span class="tally-label" style="color:${colorFor(key, colors)}">
        <strong>${count}</strong> ${escapeHtml(key)} (${pct}%)
      </span>`;
    })
    .join("");

  versionCountLabel.textContent =
    keys.length === 0 ? "no orders yet" : `${keys.length} version${keys.length === 1 ? "" : "s"} seen`;

  errCountEl.textContent = String(state.errors);

  logBody.innerHTML = state.log
    .map((entry, i) => {
      const rowClass = entry.ok ? "" : "row-error";
      const totalDisplay =
        entry.totalCents === null ? "—" : `$${(entry.totalCents / 100).toFixed(2)}`;
      const priced = entry.ok
        ? `<span class="badge" style="background:${colorFor(entry.pricedBy, colors)}22;color:${colorFor(entry.pricedBy, colors)}">${escapeHtml(entry.pricedBy)}</span>`
        : `<span class="badge error">${entry.status === 0 ? "net" : entry.status}</span>`;
      return `<tr class="${rowClass}">
        <td>${state.log.length - i}</td>
        <td>${entry.quantity}</td>
        <td>${totalDisplay}</td>
        <td>${escapeHtml(entry.ruleApplied)}</td>
        <td>${priced}</td>
      </tr>`;
    })
    .join("");
}

function pushLog(entry: LogEntry): void {
  state.log.unshift(entry);
  if (state.log.length > MAX_LOG) {
    state.log.length = MAX_LOG;
  }
}

async function sendOrder(): Promise<void> {
  const quantity = Math.max(1, Math.trunc(quantityInput.valueAsNumber || 1));
  const amountDollars = amountInput.valueAsNumber || 0;
  const amountCents = Math.round(amountDollars * 100);

  try {
    const res: OrderResponse = await placeOrder({
      customer: "ada",
      sku: "WIDGET-1",
      quantity,
      amount_cents: amountCents,
    });

    recordPriced(state.counts, res.priced_by);

    pushLog({
      quantity,
      totalCents: res.total_amount_cents,
      ruleApplied: res.rule_applied,
      pricedBy: res.priced_by,
      ok: true,
      status: 202,
    });
  } catch (err) {
    state.errors += 1;
    const status = err instanceof OrderApiError ? err.status : 0;
    pushLog({
      quantity,
      totalCents: null,
      ruleApplied: status === 0 ? "network error" : `HTTP ${status}`,
      pricedBy: "—",
      ok: false,
      status,
    });
  } finally {
    render();
  }
}

function sendMany(count: number): void {
  for (let i = 0; i < count; i++) {
    void sendOrder();
  }
}

function stopContinuous(): void {
  if (continuousTimer !== null) {
    clearInterval(continuousTimer);
    continuousTimer = null;
  }
  toggleContinuousBtn.textContent = "Start continuous (2/sec)";
  toggleContinuousBtn.classList.remove("active");
}

function startContinuous(): void {
  toggleContinuousBtn.textContent = "Stop continuous";
  toggleContinuousBtn.classList.add("active");
  continuousTimer = setInterval(() => {
    void sendOrder();
  }, CONTINUOUS_INTERVAL_MS);
}

sendOneBtn.addEventListener("click", () => void sendOrder());
sendTwentyBtn.addEventListener("click", () => sendMany(20));
toggleContinuousBtn.addEventListener("click", () => {
  if (continuousTimer === null) {
    startContinuous();
  } else {
    stopContinuous();
  }
});
resetBtn.addEventListener("click", () => {
  state.counts = new Map();
  state.errors = 0;
  state.log = [];
  colors = new Map();
  render();
});

render();
```

**`frontend/src/style.css`**

```css
:root {
  color-scheme: dark;
  --bg: #0f1115;
  --panel: #171a21;
  --border: #2a2e38;
  --text: #e6e8ec;
  --muted: #8b909c;
  --v1: #4f8cff;
  --error: #ff5c5c;
  font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
}

main {
  max-width: 760px;
  margin: 0 auto;
  padding: 2rem 1.25rem 4rem;
}

header h1 {
  margin: 0;
  font-size: 1.5rem;
}

.subtitle {
  color: var(--muted);
  margin-top: 0.25rem;
}

section {
  margin-top: 2rem;
}

.tally {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 1.25rem;
}

.tally-bar {
  display: flex;
  height: 2.5rem;
  border-radius: 6px;
  overflow: hidden;
  background: var(--border);
}

.tally-segment {
  transition: width 0.3s ease;
}

.tally-labels {
  display: flex;
  gap: 1.5rem;
  margin-top: 0.75rem;
  flex-wrap: wrap;
  font-size: 0.95rem;
}

.tally-label strong {
  font-variant-numeric: tabular-nums;
}

.tally-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 0.5rem;
  padding-top: 0.5rem;
  border-top: 1px solid var(--border);
  font-size: 0.85rem;
  color: var(--muted);
}

.tally-label.errors {
  color: var(--error);
}

.controls {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 1.25rem;
}

.field {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 0.75rem;
}

.field label {
  width: 9rem;
  color: var(--muted);
  font-size: 0.9rem;
}

.field input {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--text);
  padding: 0.4rem 0.6rem;
  width: 8rem;
}

.buttons {
  display: flex;
  gap: 0.6rem;
  flex-wrap: wrap;
  margin-top: 1rem;
}

button {
  background: var(--v1);
  color: white;
  border: none;
  border-radius: 6px;
  padding: 0.55rem 1rem;
  font-size: 0.9rem;
  cursor: pointer;
}

button:hover {
  filter: brightness(1.1);
}

button.secondary {
  background: transparent;
  border: 1px solid var(--border);
  color: var(--muted);
}

button.active {
  background: var(--error);
}

.hint {
  color: var(--muted);
  font-size: 0.85rem;
  margin: 0.75rem 0 0;
}

.log-section h2 {
  font-size: 1.05rem;
  color: var(--muted);
  font-weight: 600;
}

table.log {
  width: 100%;
  border-collapse: collapse;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 10px;
  overflow: hidden;
}

table.log th,
table.log td {
  text-align: left;
  padding: 0.5rem 0.75rem;
  border-bottom: 1px solid var(--border);
  font-size: 0.9rem;
}

table.log th {
  color: var(--muted);
  font-weight: 500;
  font-size: 0.8rem;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

tr.row-error {
  background: rgba(255, 92, 92, 0.08);
}

.badge {
  display: inline-block;
  padding: 0.15rem 0.5rem;
  border-radius: 999px;
  font-size: 0.8rem;
  font-weight: 600;
}

.badge.error {
  background: rgba(255, 92, 92, 0.18);
  color: var(--error);
}

code {
  background: rgba(255, 255, 255, 0.06);
  padding: 0.1rem 0.35rem;
  border-radius: 4px;
  font-size: 0.85em;
}
```

**`frontend/src/vite-env.d.ts`**

```ts
/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base URL for the order API. Empty string means same-origin (nginx proxies /orders). */
  readonly VITE_API_BASE: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
```

**`frontend/Dockerfile`**

```dockerfile
# syntax=docker/dockerfile:1.7
FROM docker.io/library/node:24-trixie-slim AS builder

WORKDIR /app
COPY package.json package-lock.json .npmrc ./
# --no-audit/--no-fund: this resolves through Nexus (.npmrc), not npmjs.org,
# and the lockfile makes the install reproducible, same as uv.lock elsewhere.
RUN npm ci --no-audit --no-fund

COPY tsconfig.json vite.config.ts index.html ./
COPY src ./src
RUN npm run build


# nginx-unprivileged: runs as a non-root user on port 8080 out of the box,
# matching the runAsNonRoot security context every other workload in this
# platform runs under (see services/order-api/Dockerfile).
FROM docker.io/nginxinc/nginx-unprivileged:1.27-alpine AS runtime
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 8080
```

**`frontend/.dockerignore`**

```
node_modules
dist
```

And the Pants targets over them:

**`deploy/charts/order-platform/templates/frontend.yaml`**

```yaml
{{- if .Values.frontend.enabled }}
apiVersion: v1
kind: ServiceAccount
metadata:
  name: frontend
  labels: {{- include "op.labels" (dict "name" "frontend" "root" $) | nindent 4 }}
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: frontend
  labels: {{- include "op.labels" (dict "name" "frontend" "root" $) | nindent 4 }}
spec:
  replicas: {{ .Values.frontend.replicas }}
  # Kubernetes keeps 10 superseded ReplicaSets per Deployment by default. Three
  # is enough history to roll back through and keeps `kubectl get rs` readable.
  revisionHistoryLimit: 3
  selector:
    matchLabels:
      app.kubernetes.io/name: frontend
  strategy:
    type: RollingUpdate
    rollingUpdate: { maxSurge: 1, maxUnavailable: 0 }
  template:
    metadata:
      # No checksum/config annotation: the frontend consumes no chart-managed
      # config, so there is no ConfigMap to hash and nothing that can change
      # without changing the pod template itself.
      labels: {{- include "op.labels" (dict "name" "frontend" "root" $) | nindent 8 }}
    spec:
      # Kubernetes injects a Docker-link env var per Service in this namespace:
      # ORDER_API_PORT, ORDER_WORKER_PORT, PRICING_PORT, FRONTEND_PORT — each
      # set to "tcp://<clusterIP>:<port>". Any app reading a variable of that
      # name as its own config gets a URL where it expected an integer:
      #   ValueError: invalid literal for int() with base 10: 'tcp://10.96...'
      # Env vars outrank every other config source, so the app cannot win.
      # Service links are a Docker-links relic nothing here uses.
      enableServiceLinks: false
      serviceAccountName: frontend
      imagePullSecrets:
        - name: {{ include "op.imagePullSecret" . }}
      securityContext:
        runAsNonRoot: true
        seccompProfile: { type: RuntimeDefault }
      containers:
        - name: frontend
          image: {{ include "op.image" (dict "root" $ "img" .Values.frontend.image) }}
          imagePullPolicy: IfNotPresent
          ports:
            - { name: http, containerPort: {{ .Values.frontend.port }} }
          livenessProbe:
            httpGet: { path: /, port: http }
            periodSeconds: 10
            failureThreshold: 3
          readinessProbe:
            httpGet: { path: /, port: http }
            periodSeconds: 5
            failureThreshold: 2
          resources: {{- toYaml .Values.frontend.resources | nindent 12 }}
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities: { drop: ["ALL"] }
          volumeMounts:
            # nginx-unprivileged needs to write its pid file, client body temp
            # files and cache dirs even though the image itself is read-only.
            - { name: tmp, mountPath: /tmp }
            - { name: cache, mountPath: /var/cache/nginx }
            - { name: run, mountPath: /var/run }
      volumes:
        - { name: tmp, emptyDir: {} }
        - { name: cache, emptyDir: {} }
        - { name: run, emptyDir: {} }
---
apiVersion: v1
kind: Service
metadata:
  name: frontend
  labels: {{- include "op.labels" (dict "name" "frontend" "root" $) | nindent 4 }}
spec:
  selector:
    app.kubernetes.io/name: frontend
  ports:
    - { name: http, port: 80, targetPort: http }
{{- include "op.pdb" (dict "name" "frontend" "root" $ "replicas" .Values.frontend.replicas "selector" (dict "app.kubernetes.io/name" "frontend")) }}
{{- end }}
```

> **The chart gains a `frontend` Deployment, Service and VirtualService route.** It is the first
> workload here that is not a service in the `services/` sense, and it still goes through the same
> chart — one place that knows what runs in `shop`.

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

# Not part of the Vite build — it is COPYed into the image and read by the
# port-consistency check in `checks/`.
file(name="nginx_conf", source="nginx.conf")
```

**`frontend/src/BUILD`**

```python
typescript_sources()

resource(name="style_css", source="style.css")

typescript_tests(
    name="tests",
)
```

`typescript_sources()` with no arguments takes the directory's `.ts` files, but a test file is a
different target type: `tally.test.ts` swept into `typescript_sources` is a file Pants owns and never
runs. `typescript_tests` is what makes `pants test ::` run it, and it is what `pants tailor` asks for:
`tailor --check` fails on a source file that has no target, or the wrong one. `style.css` is a
`resource`, not a source: nothing imports it in a way inference can follow.

**Every dependency in `frontend/BUILD` is listed by hand, and that is the rule for non-Python targets.** Pants
infers dependencies from *imports*, and a build script's inputs are not imports: `tsconfig.json`,
`vite.config.ts`, `index.html` and `src/style.css` are invisible to inference. Omitting a config file
fails loudly. Omitting an asset does not fail at all — Vite builds successfully in a sandbox that
simply does not contain `style.css` and emits a bundle with no styles, which is a broken page and a
green build. Enumerate the inputs; do not trust inference outside Python.

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


**`pants.ci.toml`**

```toml
# CI-only Pants configuration. Layered on top of pants.toml, not a replacement
# for it: the pipeline sets
#
#   PANTS_CONFIG_FILES=pants.ci.toml
#
# which is the mechanism the "Using Pants in CI" guide documents for exactly
# this — https://www.pantsbuild.org/stable/docs/using-pants/using-pants-in-ci
#
# Everything here is a setting that is right in a pod and wrong on a laptop.
# Nothing that affects what gets built or how it is built belongs in this file;
# a CI-only build setting is a CI-only bug waiting to happen.

[GLOBAL]
# Colors often work in CI, but the shell is usually not a TTY so Pants
# doesn't attempt to use them by default. Buildkite renders ANSI colour in the
# log, so turning them back on is free readability.
colors = true

[stats]
# Logs cache hit/miss counts and timings at the end of the run. This is the
# only visibility anyone gets into whether the Pants cache is doing anything in
# CI — without it, a run that recompiles the world looks identical to one that
# hits cache on everything, except slower.
log = true

# Coverage is deliberately NOT enabled here.
#
# `[test] use_coverage = true` is in the documented CI template, and on this
# repo it crashes Pants 2.33.0 outright:
#
#   pants/backend/go/util_rules/coverage_output.py, go_render_coverage_report
#     raw_coverage_profile=digest_contents[0].content
#   IndexError: tuple index out of range
#
# The flag is global, so it turns on Go coverage too, and the Go backend
# indexes the first element of an empty result when a test target produces no
# profile. There is no per-language switch.
#
# Nothing consumed the report anyway: `artifact_paths: "dist/*"` matches one
# level deep and the report lands two deep. Turn this on the day something
# reads it, and scope it to Python when Pants can.

[pytest]
# -vv names each test in the log, which is what you want when the only record
# of a failed CI run is its log. --no-header drops the platform/rootdir banner
# that Buildkite already shows.
args = ["-vv", "--no-header"]
```

> **A second config, not a pile of flags.** `PANTS_CONFIG_FILES` layers this over `pants.toml` in CI
> only, so the local developer experience and the CI one differ in exactly the ways written here and
> nowhere else.
The Python step and the Go step are gone. In their place, one step in `.buildkite/pipeline.sh`:

```yaml
  - label: ":hammer: lint · typecheck · test · package"
    key: verify
    agents: { queue: kubernetes }
    artifact_paths: "dist/*"
    plugins:
      - kubernetes:
          podSpec:
            imagePullSecrets:
              - name: nexus-pull
            containers:
              - image: nexus:8082/ci/pants:0.13.2-2
                resources:
                  requests: { cpu: "1", memory: 2Gi }
                  limits:   { memory: 4Gi }
                command:
                  - |
                    set -euo pipefail

                    git config --global --add safe.directory "$PWD"

                    pants update-build-files --check lint check test ::

                    python3 checks/verify_doc_listings.py .

                    helm lint --strict deploy/charts/order-platform \
                      -f deploy/env/local/values.yaml
                    helm template order-platform deploy/charts/order-platform \
                      -f deploy/env/local/values.yaml -n shop \
                      | python3 checks/verify_chart.py -

                    pants --tag=deployable package ::

                    ls -la dist/
```

Eight things about this are load-bearing:

**The step runs a prebuilt Pants image out of Nexus**, `.buildkite/pants-ci.Dockerfile`, rather than
installing Pants per build. It carries the checksum-verified `scie-pants` launcher from
[§17.3](#173-pantstoml), a Go toolchain matching `services/order-worker/go.mod` (Pants *searches* for
`go`, it does not download one), `unzip`/`zip`/`xz`, which Pants needs to unpack the tools it does
download — protoc, ruff, the Go SDK — and the two things the non-Pants checks below need: a
checksum-verified `helm` binary and `pyyaml`, the latter from the Nexus PyPI proxy like everything
else.

**`update-build-files --check` runs in the same invocation as `lint check test`.** It reformats every
`BUILD` file in memory and fails when the result differs from what is committed, which is Pants'
documented CI check for BUILD-file drift: a hand-edited `BUILD` file cannot quietly diverge from the
formatting the rest of the repo has. One invocation rather than four, because the goals share a
target-set argument and Pants runs what it can in parallel.

**`--tag=deployable` is how the package set is selected.** `::` is every target in the repo; the tag
narrows it to the ones that ship an artifact, and tags are Pants' documented mechanism for exactly
that. The alternative — globbing `services/*/BUILD` into a list of `:bin` targets — encodes a naming
convention in a shell pipeline, outside the build system, where nothing checks it: a target named
anything else is silently not packaged, and a `BUILD` file with no `pex_binary` at all fails the whole
step. With the tag, a target declares itself deployable in the one file that already describes it, so
the Backstage paved path ([§14.6](phase-5-developer-portal.md#146-paved-path-1--a-new-service)) adds a
service that CI packages without CI knowing it exists.

**`checks/verify_doc_listings.py` runs here rather than as a Pants test.** It reads the whole checkout;
a Pants sandbox holds only declared dependencies, so every file listing in `docs/` would read as
missing inside one.

**The chart is rendered here, and it is the only place the build renders it at all.** `helm lint
--strict` validates structure and `helm template` produces the manifests; `checks/verify_chart.py`
([§19.6](#196-two-checks-nothing-else-would-catch)) then reads them for the defects neither command
can see. Both run against the local env overlay, so the values CI rewrites are the values checked.

**`pants package` runs here, not in the image build.** The Buildah pods below it contain Buildah and
nothing else — no Python, no Go, no Node, no compiler. They `buildkite-agent artifact download` the
artifacts and copy them into an image. That is why every Dockerfile under `services/` is now four
lines, and why the **build context is `dist/`** rather than the source tree:

```sh
buildah bud \
  --tls-verify=false \
  --file services/$SVC/Dockerfile \
  --tag "$REGISTRY/shop/$SVC:$SHA" \
  dist
```

The last argument is the context. Each Dockerfile therefore `COPY`s its artifact by bare name —
`order-api.pex`, `pricing.pex`, `order-worker` — which is what the `output_path` on each Pants target
exists to guarantee. A `COPY services/order-api/…` would fail with "no such file or directory" on a
path that exists perfectly well in the repo.

`order-worker`'s Dockerfile is the whole of it, and it has one flag the PEX images do not need:

```dockerfile
# syntax=docker/dockerfile:1.7
FROM gcr.io/distroless/static-debian12:nonroot
COPY --chmod=0755 order-worker /order-worker
USER 65532:65532
EXPOSE 9090
ENTRYPOINT ["/order-worker"]
```

`--chmod=0755` is required, not cosmetic. `pants package` writes an executable binary, but the verify
step uploads it as a Buildkite artifact and the build step downloads it, and **artifact transfer does
not preserve file modes** — the bit is lost between the two pods and the container fails at runtime
with `exec: "/order-worker": permission denied`, with no application output at all. The PEX services
are immune only because they are invoked as `python /app/x.pex` rather than executed directly.

**The build steps are discovered too, by a different mechanism.** Packaging selects on a tag inside
Pants; the image builds cannot, because Buildah knows nothing about targets. A directory under
`services/` with a `BUILD` file and a `Dockerfile` is a service, and that is the whole contract:

```sh
SERVICES="$(cd services && ls -d */ 2>/dev/null | sed 's#/##' | while read -r s; do
  [ -f "$s/BUILD" ] && [ -f "$s/Dockerfile" ] && echo "$s"
done | sort | tr '\n' ' ')"
```

`BUILD` rather than `Dockerfile` alone is the honest signal: a directory Pants does not know about
cannot be linted, tested or packaged, so it is not a service this pipeline can deliver. The Backstage
skeleton emits both files, which is what lets the paved path
([§14.6](phase-5-developer-portal.md#146-paved-path-1--a-new-service)) add a service without anyone
editing CI.

**There are no `--build-arg`s.** The version a running service reports comes from `SERVICE_VERSION`,
set by the Helm chart from the image tag
([§10.1](phase-1-the-application.md#101-one-chart-two-workloads)) — one mechanism, applied uniformly
to Python and Go alike, rather than a Go-specific link-time stamp that only one of the four images
could ever have carried.

The frontend and the portal get their own steps: neither consumes a Pants artifact, and the portal's
build is measured in double-digit minutes, so it is `branches: "main"` only.

### 19.6 Two checks nothing else would catch

Some facts span two files in two languages with nothing connecting them. Those get a test.

**The OpenAPI spec is derived, not authored.** Backstage's catalog reads `services/order-api/openapi.json`
from git, but FastAPI builds that document from route signatures at runtime, so the checked-in copy
can only ever be a snapshot. `services/order-api/BUILD` makes regenerating it a target, and a test
fails when the two drift. The dumper, the test, and the `BUILD` file those two need — which now
carries four targets it did not at [§17.5](#175-targets-and-the-two-files-that-decide-whether-the-checks-pass):

**`services/order-api/openapi_dump.py`**

```python
"""Print order-api's OpenAPI document to stdout.

The Backstage catalog needs a spec file it can read from git (`API/orders` in
`catalog-info.yaml`). FastAPI builds that document from the route signatures at
runtime, so the checked-in copy is derived, not authored:

    pants run services/order-api:dump-openapi > services/order-api/openapi.json

`tests/test_openapi_spec.py` fails if the two drift, which is the only thing
keeping the catalog honest — a hand-maintained API spec is a lie with a
timestamp on it.
"""

import json
import os
import sys

# Settings are read at import time and fail closed on a missing broker list
# (§3.1). Nothing here connects to anything — the document is built from the
# route signatures — so placeholders are enough to get the module imported.
os.environ.setdefault("KAFKA_BROKERS", "localhost:9092")
os.environ.setdefault("S3_BUCKET", "unused")
os.environ.setdefault("ORDER_SIGNING_KEY", "unused")

from order_api.main import app  # noqa: E402


def main() -> None:
    json.dump(app.openapi(), sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
```

**`services/order-api/tests/test_openapi_spec.py`**

```python
"""The checked-in OpenAPI document must match what the app actually serves.

`catalog-info.yaml` points Backstage at `services/order-api/openapi.json`. A spec
that drifts from the code is worse than no spec: the portal keeps rendering it,
confidently, long after the route changed. This test is the thing that stops
that, and it is the reason the file is generated rather than written.
"""

import json
import os
from pathlib import Path

os.environ.setdefault("KAFKA_BROKERS", "localhost:9092")
os.environ.setdefault("S3_BUCKET", "test-bucket")
os.environ.setdefault("ORDER_SIGNING_KEY", "test-key")

from order_api.main import app  # noqa: E402

# tests/ sits at the source root (`/services/order-api`), so the spec is one
# level up from this file inside the Pants sandbox.
SPEC = Path(__file__).parent.parent / "openapi.json"


def test_checked_in_spec_matches_the_running_app():
    assert SPEC.exists(), (
        f"{SPEC.name} is missing; run `pants run services/order-api:dump-openapi`"
    )
    assert json.loads(SPEC.read_text()) == app.openapi(), (
        "openapi.json is stale. Regenerate it:\n"
        "  pants run services/order-api:dump-openapi > services/order-api/openapi.json"
    )
```

**`services/order-api/BUILD`**

```python
python_sources(
    name="lib",
    sources=["order_api/**/*.py"],
)

python_sources(
    name="tools",
    sources=["openapi_dump.py"],
    dependencies=[":lib"],
)

pex_binary(
    name="dump-openapi",
    entry_point="openapi_dump.py",
    dependencies=[":tools"],
)

resource(
    name="openapi-spec",
    source="openapi.json",
)

python_tests(
    name="tests",
    # `!tests/__init__.py`: it's a namespace marker, not a test — including it
    # makes Pants generate a `python_test` target for it that pytest then fails
    # with "no tests collected".
    sources=["tests/**/*.py", "!tests/__init__.py"],
    # `:openapi-spec` is a resource, not code, so nothing infers it — the drift
    # test reads it off disk by path.
    dependencies=[":lib", ":openapi-spec"],
)

pex_binary(
    name="bin",
    # Declares this target as something CI ships. `pants --tag=deployable
    # package ::` selects on it, so a service is packaged the moment it says
    # so itself — no list in the pipeline to keep in sync.
    tags=["deployable"],
    entry_point="order_api.main:main",
    dependencies=[":lib"],
    # The cluster runs linux/aarch64, not this macOS laptop. Without this,
    # `pants package` resolves macOS wheels for native deps (grpcio,
    # pydantic-core, uvloop, watchfiles) that import-fail in the container.
    complete_platforms=["3rdparty/python:linux-platform"],
    # Land in dist/ under a predictable name so dist/ can be used
    # directly as the Buildah build context and the Dockerfile can COPY by
    # name. Default would be dist/services.<name>/bin.pex.
    output_path="order-api.pex",
)
```

```bash
pants run services/order-api:dump-openapi > services/order-api/openapi.json
```

`:openapi-spec` is a `resource`, not code, so nothing infers it — the drift test reads it off disk by
path, which is why `python_tests` lists it explicitly in `dependencies`. A hand-maintained API spec is
a lie with a timestamp on it.

**The frontend's proxy port must match the port `order-api`'s Service publishes.** `frontend/nginx.conf`
says `proxy_pass http://order-api.shop.svc.cluster.local:80/orders`; the chart says
`- { name: http, port: 80, targetPort: http }`. Point nginx at 8000 — order-api's *container* port,
which nothing serves on the ClusterIP — and every order in the dashboard reads `HTTP 502` while a
direct `curl` at order-api returns 202, sending you to look at the wrong service entirely. The chart
is valid, the nginx config is valid, both images build, every pod is Ready. `checks/verify_chart.py`
asserts the two agree.

**Check the rendered chart, never the template.** A template read as text is
`targetPort: {{ .Values.orderApi.port }}` — a text check either hard-codes the answer it is supposed
to discover or reimplements Helm's evaluation. `helm template` first, parse the manifests, then read
the port the cluster actually gets. That is the flow Helm documents for debugging a chart and it is
the one the check uses:

```bash
helm template order-platform deploy/charts/order-platform \
  -f deploy/env/local/values.yaml -n shop | python3 checks/verify_chart.py -
```

Two more assertions of the same shape ride along in that script, because rendering the chart is the
expensive part and both need the same manifests: a probe whose `httpGet`/`tcpSocket` names a port the
container does not declare, and a Service whose `targetPort` names a port no selected pod declares.
Each half is valid YAML on its own, so both render clean, lint clean, and fail only when the kubelet
tries to resolve the name.

`verify_chart.py` runs as a plain script rather than through Pants, for the same reason
`verify_doc_listings.py` does: it reads files a hermetic sandbox would not contain. That has two
consequences in the repo. It still needs an owning target, or `pants tailor --check` reports the file
`checks/` is a Python package, so it needs **`checks/__init__.py`** — an empty file — and its scripts need an owning target, or `pants tailor --check` reports them as unowned. Hence the glob in **`checks/BUILD`**:

```python
python_sources(
    name="lib",
    # Everything that is not a test. `verify_chart.py` is not imported by the
    # test suite — it runs in CI against a rendered chart — but it still needs
    # an owning target, or `pants tailor --check` reports the file as unowned.
    sources=["*.py", "!test_*.py"],
)

python_tests(
    name="tests",
    sources=["test_*.py"],
    # Prose read as plain text. Nothing here is reachable by import, which is
    # exactly why the two editions of the tutorial were free to drift apart.
    dependencies=[
        ":lib",
        "docs:docs",
        "//:single-edition",
    ],
)
```

And its one third-party import, `yaml`, is installed in the CI image rather than in the Python
resolve, so mypy has nothing to load. That is a per-module exception in `mypy.ini` with the reason
stated, not a global `ignore_missing_imports`:

```ini
[mypy-yaml]
ignore_missing_imports = true
```

That is the pattern worth taking away: **when a fact is duplicated across a language boundary, the
monorepo lets you assert it in a check that runs on every build.** It is the same argument as
[§18.2](#182-generate-and-look-at-what-came-out), applied to config instead of to a `.proto`.

### 19.7 Commit

Two files are now dead. `order-api`'s dependencies are resolved from `locks/python-default.lock`
by Pants, so the uv pair that used to do it describes a build nobody runs — and a stale lockfile is
worse than none, because the next person to read it will believe it.

```bash
git rm services/order-api/pyproject.toml services/order-api/uv.lock
```

Then verify and commit:

```bash
pants lint check test ::
pants package services/order-api:bin services/order-worker:bin services/pricing:bin
ls -la dist/

git add pants.toml mypy.ini 3rdparty locks protos services frontend checks .buildkite deploy
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
[§9.9](phase-4-service-mesh.md#99-canary-two-versions-of-pricing-behind-one-service) needs to shift
traffic between two versions of `pricing` and let you watch the split move in a browser. Go back and
do that now; it is the part of [Phase 4](phase-4-service-mesh.md) you could not run yet.

**Next: [Phase 6 — Operating it](phase-6-operating.md).** Now find out what happens when it breaks.

[← All phases](README.md) · [← Phase 5 — Making it someone else's platform](phase-5-developer-portal.md) · [Phase 6 — Operating it, and taking it down →](phase-6-operating.md)

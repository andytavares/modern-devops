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
curl -fsSL -o /usr/local/bin/pants \
  https://github.com/pantsbuild/scie-pants/releases/download/v0.13.2/scie-pants-macos-aarch64
echo "a6f3231413ca1f793caffa621171a4b1a0158e7488cd0b5bb3e742cb99cc72a8  /usr/local/bin/pants" \
  | shasum -a 256 -c -
chmod 755 /usr/local/bin/pants
```

> **This one binary comes from outside the choke point, deliberately and once.** Everything Pants
> then resolves — Python wheels, Go modules — goes through [[sonatype-nexus]]
> ([§5.1](phase-0-foundations.md#51-what-nexus-is-actually-for)), and CI does not repeat this
> download at all: `.buildkite/pants-ci.Dockerfile` bakes the same checksum-verified launcher into an
> image that lives in Nexus ([§19.5](#195-one-ci-step-instead-of-two)). A pinned, hashed, one-time
> fetch is an honest compromise; `curl … | bash` on every build is not.

The configuration, comments stripped:

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

pants_ignore.add = [
  "/deploy/backstage/templates",
  "/portal",
  "/wiki",
  "/raw",
  "/docs",
]

[source]
root_patterns = ["/", "/services/*", "/protos"]

[python]
interpreter_constraints = [">=3.13,<3.14"]
enable_resolves = true
default_resolve = "python-default"

[python.resolves]
python-default = "locks/python-default.lock"

[python-bootstrap]
search_path = ["<PYENV>", "<PATH>", "/opt/homebrew/opt/python@3.13/libexec/bin"]

[python-repos]
indexes = ["http://nexus:8081/repository/pypi-proxy/simple"]

[golang]
cgo_enabled = false
subprocess_env_vars = [
  "GOPROXY=http://nexus:8081/repository/go-proxy",
  "GOSUMDB=off",
  "GOFLAGS=-mod=mod",
  "HOME",
  "PATH",
]

[python-protobuf]
generate_type_stubs = true

[mypy]
install_from_resolve = "python-default"

[test]
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
- **`[python-bootstrap] search_path` names the Homebrew path explicitly.** `brew install python@3.13`
  puts the unversioned `python` in `libexec/bin`, which is deliberately off `PATH`, and Pants' default
  search will not find it. `<PYENV>` and `<PATH>` are the defaults and must be repeated, not replaced.
- **`[python-repos]` and `[golang]` both point at Nexus**, for the same reason `uv` did
  ([§5.1](phase-0-foundations.md#51-what-nexus-is-actually-for)). `GOSUMDB=off`
  because the public checksum database is unreachable through a private proxy — the same trade, and
  the same caveat, as [§12.5](phase-3-delivery.md#125-the-pipeline).
- **`[golang] cgo_enabled = false` is mandatory.** Pants defaults it to *true*, which links
  `order-worker` dynamically against libc. `gcr.io/distroless/static-debian12` has neither libc nor a
  dynamic loader, so the pod dies with `exec /order-worker: no such file or directory` on a file that
  is present and executable.
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
def build_server() -> tuple[grpc.Server, health.HealthServicer]:
    """Assemble the gRPC server: pricing, health checking and reflection.

    Nothing here binds a port or starts a thread, so tests can build the exact
    server the process runs and drive it on an ephemeral port.
    """
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    pricing_pb2_grpc.add_PricingServicer_to_server(PricingServicer(), server)

    health_servicer = health.HealthServicer(
        experimental_non_blocking=True,
        experimental_thread_pool=futures.ThreadPoolExecutor(max_workers=10),
    )
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)
    for service_name in ("", PRICING_SERVICE_NAME):
        health_servicer.set(service_name, health_pb2.HealthCheckResponse.SERVING)

    reflection.enable_server_reflection(
        (PRICING_SERVICE_NAME, HEALTH_SERVICE_NAME, reflection.SERVICE_NAME),
        server,
    )
    return server, health_servicer
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

#### Wiring `order-api` to it

A pricing service nothing calls is a pricing service you cannot canary. The rest of this section is
the caller side: the address, the client, the metric, the call, and the tests. Do it now — everything
downstream ([§19.4](#194-the-frontend-vite-and-a-live-tally),
[§9.8](phase-4-service-mesh.md#98-canary-two-versions-of-pricing-behind-one-service)) depends on it.

**Address and deadlines.** `order-api`'s settings module is now a `pydantic-settings` `BaseSettings`
subclass. Hand-rolled environment parsing is the job that library exists to do, and it is the approach
FastAPI documents. Replace [§3.1](phase-1-the-application.md#31-order-api-python--fastapi)'s version
with this, and add `pydantic-settings` to `3rdparty/python/requirements.txt`:

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
    aws_region: str = Field(default="us-east-1", validation_alias="AWS_DEFAULT_REGION")
    aws_endpoint_url: str | None = None

    signing_key: str = Field(validation_alias="ORDER_SIGNING_KEY")

    service_version: str = "dev"
    order_api_port: int = 8000

    pricing_addr: str = "pricing.shop.svc.cluster.local:50051"
    pricing_timeout_seconds: float = 2.0
    pricing_health_timeout_seconds: float = 1.0


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
[§9.8](phase-4-service-mesh.md#98-canary-two-versions-of-pricing-behind-one-service) starts injecting
delays. `pricing_health_timeout_seconds` is separate and shorter: readiness must answer on the probe's
schedule, not on the order path's.

**The client.** Add the imports and the metric to `main.py`:

**`services/order-api/order_api/main.py`**

```python
import grpc
from fastapi.concurrency import run_in_threadpool
from grpc_health.v1 import health_pb2, health_pb2_grpc  # type: ignore[import-untyped]
from prometheus_client import Counter, Histogram, make_asgi_app
from shop.v1 import pricing_pb2, pricing_pb2_grpc
```

`grpcio-health-checking` ships no `py.typed` marker, so the ignore goes on the import rather than in a
global `ignore_missing_imports` — which would silence real typos in every other module too. Add
`grpcio-health-checking` and `grpcio-reflection` to `3rdparty/python/requirements.txt`; they are
first-party gRPC add-ons shipped as separate packages.

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

**`3rdparty/python/BUILD`** (comments stripped):

```python
python_requirements(
    name="reqs",
    source="requirements.txt",
)

file(
    name="linux-platform",
    source="linux.json",
)
```

**`services/pricing/BUILD`**, the `pex_binary` (comments stripped):

```python
pex_binary(
    name="bin",
    tags=["deployable"],
    entry_point="pricing/main.py:main",
    dependencies=[":lib"],
    complete_platforms=["3rdparty/python:linux-platform"],
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
> you would have to build the wheel yourself and host it in [[sonatype-nexus]]. This is not a Pants
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
read-only. From `deploy/charts/order-platform/templates/pricing.yaml`:

```yaml
          env:
            # ... the service's own config ...
            - name: PEX_ROOT
              value: "/tmp/pex"
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities: { drop: ["ALL"] }
          volumeMounts:
            - { name: tmp, mountPath: /tmp }
      volumes:
        - { name: tmp, emptyDir: {} }
```

Set `PEX_ROOT` rather than relying on `/tmp` being writable by default — the fallback order is an
implementation detail, and an explicit path is a thing a reader can find. **Every service packaged as
a PEX needs both halves** — `order-api.yaml`, `pricing.yaml` and `scaffolded.yaml` all carry them, so
a service that arrives through the paved path gets them without anyone remembering to ask.

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

It is the same class of problem as `nginx-unprivileged` needing writable `/tmp`, `/var/cache/nginx`
and `/var/run`: both render perfectly under `helm template`, pass `kubectl apply --dry-run=server`,
and fail only at runtime. **Dry-run validates schema, not whether the process can start.**

```bash
kubectl -n shop get pods -l app.kubernetes.io/name=pricing
# pricing-v1-... 2/2 Running     (2/2 — the sidecar is the second container)
# pricing-v2-... 2/2 Running
```

### 19.4 The frontend: Vite, and a live tally

`frontend/` is a [[vite]] + TypeScript page with no framework. It POSTs orders to `order-api`,
tallies the `priced_by` on each response, and draws a bar. A 90/10 → 50/50 weight change is visible in a
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

# Not part of the Vite build — it is COPYed into the image and read by the
# port-consistency check in `checks/`.
file(name="nginx_conf", source="nginx.conf")
```

**Every dependency there is listed by hand, and that is the rule for non-Python targets.** Pants
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
              - image: nexus:8082/ci/pants:0.13.2
                resources:
                  requests: { cpu: "1", memory: 2Gi }
                  limits:   { memory: 4Gi }
                command:
                  - |
                    set -euo pipefail

                    git config --global --add safe.directory "$PWD"

                    pants lint check test ::

                    python3 checks/verify_doc_listings.py .

                    pants --tag=deployable package ::

                    ls -la dist/
```

Six things about this are load-bearing:

**The step runs a prebuilt Pants image out of Nexus**, `.buildkite/pants-ci.Dockerfile`, rather than
installing Pants per build. It carries the checksum-verified `scie-pants` launcher from
[§17.3](#173-pantstoml), a Go toolchain matching `services/order-worker/go.mod` (Pants *searches* for
`go`, it does not download one), and `unzip`/`zip`/`xz`, which Pants needs to unpack the tools it does
download — protoc, ruff, the Go SDK.

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
fails when the two drift:

```python
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
is valid, the nginx config is valid, both images build, every pod is Ready. So `checks/` at the repo
root asserts the two agree:

```python
python_tests(
    name="tests",
    sources=["test_*.py"],
    # Config files from two other directories, read as plain text. Nothing
    # infers these — there is no import to follow, which is exactly why the two
    # were free to drift apart in the first place.
    dependencies=[
        "frontend:nginx_conf",
        "deploy/charts/order-platform:order-api-template",
    ],
)
```

**`deploy/charts/order-platform/BUILD`**, and note where it is *not*:

```python
# Deliberately NOT in templates/. Helm renders every file under templates/ as a
# manifest, so a BUILD file there fails the whole chart with
# `YAML parse error on order-platform/templates/BUILD`.
file(name="order-api-template", source="templates/order-api.yaml")
```

That is the pattern worth taking away: **when a fact is duplicated across a language boundary, the
monorepo lets you assert it in a unit test.** It is the same argument as
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

git add pants.toml 3rdparty locks protos services frontend checks .buildkite deploy
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

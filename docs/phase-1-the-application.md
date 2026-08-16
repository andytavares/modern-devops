# Phase 1 — The application, running

[← All phases](README.md) · [← Phase 0 — Foundations](phase-0-foundations.md) · [Phase 2 — Seeing what it does →](phase-2-observability.md)

> **Where this starts:** an empty cluster with a registry.
> **Where it ends:** `curl -X POST http://shop.localtest.me/orders` returns `202`, a JSON object
> lands in S3, and a row appears in DynamoDB.

This is the phase that makes the rest worth doing. Two services, the backing infrastructure they
actually need, packaged as one Helm chart and installed **by hand**.

By hand is deliberate. `helm install` from your laptop is how most teams really deploy before they
adopt GitOps, and it is worth feeling the specific things wrong with it — you have to be present, you
have to hold the image tag in your head, and nothing anywhere records what you did — before
[Phase 3](phase-3-delivery.md) takes it away from you. A tool whose value you have not felt the
absence of is a tool you will misconfigure.

**Order matters here and it is not arbitrary.** The services come first so you know what they need;
then their dependencies, in the order the services touch them; then packaging; then the install.

---

## 3. The applications

Write the software first. A platform with nothing to deploy teaches you nothing about deploying.

Both services follow the same contract, because *consistency across runtimes is the point of a platform*:

- Config comes from environment variables only. No config files in images.
- `GET /healthz` — liveness. Process is alive.
- `GET /readyz` — readiness. Dependencies are reachable.
- `GET /metrics` — Prometheus text format.
- Logs to stdout, structured JSON.
- Non-root user in the image.

### 3.1 order-api (Python / FastAPI)

Accepts an order, persists the raw payload to S3, publishes an event to Kafka.

**`services/order-api/pyproject.toml`**

```toml
[project]
name = "order-api"
version = "0.1.0"
requires-python = ">=3.13,<3.14"
dependencies = [
    "fastapi[standard]==0.139.2",
    "aiokafka==0.12.0",
    "boto3==1.40.11",
    "prometheus-client==0.23.1",
    "pydantic==2.11.7",
    "pydantic-settings==2.7.1",
]

[dependency-groups]
dev = [
    "pytest==8.4.1",
    "httpx==0.28.1",
    "ruff==0.12.8",
]

# Declared here, not only as a CI env var, so `uv.lock` records this registry
# and the lock validates identically on a laptop and in the build pod. uv
# refuses a lockfile whose registries aren't in the current index config, so
# setting UV_INDEX_URL in CI alone is not enough.
[[tool.uv.index]]
url = "http://nexus:8081/repository/pypi-proxy/simple"
default = true

[tool.uv]
# Plain HTTP, per §5.8. Without this uv refuses the index outright.
allow-insecure-host = ["nexus"]

[tool.ruff]
line-length = 100

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["order_api"]
```

> **Why the index lives here and not in the CI environment.** It is tempting to leave `pyproject.toml`
> pointing at PyPI and set `UV_DEFAULT_INDEX` (or its deprecated predecessor `UV_INDEX_URL`) only in
> the pipeline. That combination cannot work, and the failure is delayed until CI. `uv.lock` records
> the registry each package came from, and uv refuses a lockfile whose registries aren't in the
> current index configuration — from uv's own resolver:
>
> > *"If the user provided at least one index URL (from the command line, or from a configuration
> > file), don't use the existing lockfile if it references any registries that are no longer included
> > in the current configuration."*
>
> So a lock generated on your laptop against `pypi.org` can never satisfy a build that points uv at
> Nexus, and `uv sync --locked` fails with **"The lockfile at `uv.lock` needs to be updated"** — on a
> lockfile you just committed and which passes locally. Declaring the index in `pyproject.toml` puts
> it *in the lock*, so both environments agree and CI needs no uv-specific environment at all.
>
> Note this pins `nexus:8081` into the project, which is only resolvable in this environment
> ([§5.7](phase-0-foundations.md#57-make-nexus-resolve-from-your-laptop)). That is the honest cost of a hermetic index, and
> it is the same trade a real internal PyPI mirror makes.

Create the package directories:

```bash
mkdir -p services/order-api/order_api services/order-api/tests
touch services/order-api/order_api/__init__.py services/order-api/tests/__init__.py
```

The package is `order_api`, not `app`. Name it after the service from the start: a generic top-level
package name collides with every other service's the moment they share a source root.

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


# pydantic's metaclass is a PEP 681 `dataclass_transform`, so mypy synthesises an
# `__init__` taking every field and reports the three required ones as missing
# arguments. They are not passed as arguments — BaseSettings reads them from the
# environment, which is the entire point of the class.
settings = Settings()  # type: ignore[call-arg]
```

> **Why fail at import.** A pod that starts successfully and then 500s on every request is much harder to diagnose than one that crash-loops with `1 validation error for Settings / kafka_brokers / Field required`. Crash-loop is a *good* failure mode: `kubectl get pods` shows it, Argo CD shows it degraded, and the alert fires immediately. Degrading quietly is the bad one. A hand-rolled loader can do this too — what it cannot do for free is report *all* the missing variables in one message, coerce `PRICING_TIMEOUT_SECONDS` to a float and reject `"soon"`, or stay honest about types as the class grows. Config parsing is validation, and you already have a validation library in the image.

> **`validation_alias` and why two fields need it.** Field name → variable name is a mechanical upper-casing, which is right until the variable is owned by someone else. `AWS_DEFAULT_REGION` belongs to the AWS SDKs — every tool in the container reads it — so the field takes the alias rather than the variable taking our name. `ORDER_SIGNING_KEY` is the reverse case: the *variable* is namespaced per service (it comes from an `ExternalSecret` in a shared namespace, §7.6) while the field stays `signing_key`. Note that `validation_alias` replaces the default name; it does not add an alternative to it.

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
from aiokafka import AIOKafkaProducer
from botocore.config import Config as BotoConfig
from fastapi import FastAPI, HTTPException
from fastapi.concurrency import run_in_threadpool
from prometheus_client import Counter, Histogram, make_asgi_app
from pydantic import BaseModel, Field

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

# ---------- state ----------
state: dict = {"producer": None, "s3": None, "ready": False}


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
        acks="all",              # do not consider a write done until all ISRs have it
        enable_idempotence=True, # no duplicates on internal retry
        linger_ms=5,
    )
    await producer.start()
    state["producer"] = producer
    state["ready"] = True
    log.info("order-api started version=%s", settings.service_version)
    try:
        yield
    finally:
        state["ready"] = False
        await producer.stop()
        log.info("order-api stopped")


app = FastAPI(title="order-api", version=settings.service_version, lifespan=lifespan)


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
def readyz() -> dict:
    """Readiness: dependencies are up. Kubernetes pulls us out of the Service if this fails."""
    if not state["ready"]:
        raise HTTPException(status_code=503, detail="dependencies not ready")
    return {"status": "ready"}


# prometheus_client ships an ASGI app for this; mounting it is what its docs
# prescribe for FastAPI. Mounting also keeps /metrics out of the OpenAPI schema,
# where a scrape endpoint has no business being.
app.mount("/metrics", make_asgi_app())


@app.post("/orders", status_code=202)
async def create_order(order: OrderIn) -> dict:
    started = time.perf_counter()
    order_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()

    payload = order.model_dump() | {"order_id": order_id, "created_at": created_at}
    body = json.dumps(payload, separators=(",", ":")).encode()

    # Sign the payload with a key that only ever exists in OpenBao.
    signature = hmac.new(
        settings.signing_key.encode(), body, hashlib.sha256
    ).hexdigest()

    key = f"orders/{created_at[:10]}/{order_id}.json"
    try:
        # boto3 is synchronous. Calling it directly from an `async def` would
        # block the event loop for the whole S3 round trip — every other
        # in-flight request, and the liveness probe with them. FastAPI runs
        # plain `def` endpoints in a threadpool for exactly this reason; this
        # handler needs `await` for Kafka, so it reaches for the same threadpool
        # explicitly.
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
    except Exception:
        ORDERS_RECEIVED.labels(result="error").inc()
        log.exception("failed to ingest order_id=%s", order_id)
        raise HTTPException(status_code=502, detail="downstream failure")
    finally:
        ORDER_LATENCY.observe(time.perf_counter() - started)

    ORDERS_RECEIVED.labels(result="ok").inc()
    log.info("accepted order_id=%s key=%s", order_id, key)
    return {"order_id": order_id, "status": "accepted", "s3_key": key}
```

Three decisions worth naming:

- **S3 write happens before the Kafka publish.** If the publish fails, we've stored an orphan object — cheap and recoverable. If we published first and the S3 write failed, the worker would consume an event pointing at an object that doesn't exist. Order your side effects so the recoverable failure is the likely one.
- **`acks="all"` + idempotence.** The default is faster and will silently lose writes when a broker restarts. On a 3-broker cluster you want durability; on a benchmark you want speed. Know which one you configured.
- **Partition key = order id.** Kafka only guarantees ordering *within a partition*. Keying by order id means all events for one order land on one partition, so a later "order cancelled" can never overtake "order created".

**`services/order-api/tests/test_api.py`**

```python
import os

# Settings are read at import time, so the environment must be set first.
os.environ.setdefault("KAFKA_BROKERS", "localhost:9092")
os.environ.setdefault("S3_BUCKET", "test-bucket")
os.environ.setdefault("ORDER_SIGNING_KEY", "test-key")

import pytest  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from order_api.main import OrderIn, app, healthz, state  # noqa: E402


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
```

> These are deliberately thin. The point of CI tests in this tutorial is to prove the *pipeline* runs them and fails the build when they fail — not to demonstrate test design. Break one on purpose in [§15.4](phase-6-operating.md#154-break-it-on-purpose).

**`services/order-api/Dockerfile`**

```dockerfile
# syntax=docker/dockerfile:1.7
FROM docker.io/library/python:3.13-slim AS builder

# uv resolves and installs an order of magnitude faster than pip, and writes a
# lockfile we can commit for reproducible builds.
COPY --from=ghcr.io/astral-sh/uv:0.12.1 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app
COPY pyproject.toml uv.lock ./
# --no-install-project: dependencies only, so this layer caches across code changes.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project --no-dev

COPY order_api ./order_api
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev


FROM docker.io/library/python:3.13-slim AS runtime
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin appuser
WORKDIR /app
COPY --from=builder --chown=10001:10001 /app /app
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
USER 10001
EXPOSE 8000
CMD ["uvicorn", "order_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

> **Tradeoff — multi-stage build.** The builder stage carries uv and build caches; the runtime stage carries only the virtualenv and your code. Costs you ~15 lines of Dockerfile, saves ~200 MB per image and removes the build toolchain from the attack surface. Always worth it. The `--mount=type=cache` lines require BuildKit, which is the default in Docker 23+ and is supported by Buildah — but note that cache mounts are *builder-local*, so they help your laptop and do nothing for a cold CI pod. Real CI caching means a shared cache backend, which is out of scope here.

Pin the interpreter before anything else, then generate the lockfile the Dockerfile requires:

```bash
cd services/order-api
uv python pin 3.13     # writes .python-version; uv downloads 3.13 if you don't have it
uv lock
uv sync --dev          # creates .venv for local work
uv run pytest -q       # should pass
cd ../..
```

> **`uv python pin` and the `<3.14` bound are not belt-and-braces, they do different jobs — and skipping them produces a spectacular, misleading failure.** Without them, uv picks the newest interpreter on your machine that satisfies `requires-python`. If that is newer than the newest CPython `pydantic-core` publishes wheels for, uv falls back to **building it from source**, and you get a wall of Rust output ending in `the configured Python interpreter version (3.14) is newer than PyO3's maximum supported version (3.13)`. Nothing in that message mentions Python pinning, and the obvious readings — "pydantic is broken", "I need Rust" — are both wrong.
>
> The two mechanisms:
> - **`.python-version`** (written by `uv python pin`) selects the interpreter for *this* project's venv. It is what stops your local environment drifting when Homebrew upgrades `python3` underneath you.
> - **`requires-python = ">=3.13,<3.14"`** is packaging metadata: it constrains *resolution*, so the lockfile can never resolve against an interpreter the container won't run.
>
> The deeper point is dev/prod parity: the Dockerfile above says `FROM python:3.13-slim`. An unpinned local interpreter means you test on one Python and ship on another, and you find out at the worst time. **Pin the interpreter in the same commit that pins the dependencies.**

### 3.2 order-worker (Go)

Consumes `orders`, writes to DynamoDB, exports metrics.

```bash
cd services/order-worker
go mod init github.com/<your-github-user>/modern-devops/services/order-worker
go get github.com/twmb/franz-go/pkg/kgo@latest
go get github.com/aws/aws-sdk-go-v2/config@latest
go get github.com/aws/aws-sdk-go-v2/service/dynamodb@latest
go get github.com/prometheus/client_golang/prometheus@latest
go get github.com/prometheus/client_golang/prometheus/promauto@latest
go get github.com/prometheus/client_golang/prometheus/promhttp@latest
cd ../..
```

> **Why franz-go and not `segmentio/kafka-go` or `confluent-kafka-go`.** franz-go is pure Go (no cgo, so `CGO_ENABLED=0` static builds and scratch images just work), implements the full modern protocol including KRaft-era features, and is actively maintained with a large user base. `confluent-kafka-go` wraps librdkafka — battle-tested but drags cgo into your build. `segmentio/kafka-go` is fine but has thinner coverage of newer protocol features.

**`services/order-worker/main.go`**

```go
// Command order-worker consumes order events from Kafka and persists them to DynamoDB.
package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"strconv"
	"strings"
	"sync/atomic"
	"syscall"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	awsconfig "github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	ddbtypes "github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
	"github.com/prometheus/client_golang/prometheus/promhttp"
	"github.com/twmb/franz-go/pkg/kgo"
)

var (
	processed = promauto.NewCounterVec(prometheus.CounterOpts{
		Name: "orders_processed_total",
		Help: "Order events consumed from Kafka and written to DynamoDB.",
	}, []string{"result"})

	processDuration = promauto.NewHistogram(prometheus.HistogramOpts{
		Name:    "order_process_duration_seconds",
		Help:    "Time to persist one order event.",
		Buckets: prometheus.DefBuckets,
	})

	lag = promauto.NewGauge(prometheus.GaugeOpts{
		Name: "order_event_age_seconds",
		Help: "Age of the most recently processed event, from created_at to write time.",
	})
)

// putItemAPI is the part of *dynamodb.Client that this service uses. Depending
// on the interface rather than the concrete client is what lets the commit
// tests drive a failing write.
type putItemAPI interface {
	PutItem(ctx context.Context, params *dynamodb.PutItemInput, optFns ...func(*dynamodb.Options)) (*dynamodb.PutItemOutput, error)
}

// recordMarker is the part of *kgo.Client that this service uses to checkpoint
// progress. See AutoCommitMarks in main for why marking, not committing, is the
// per-record operation.
type recordMarker interface {
	MarkCommitRecords(rs ...*kgo.Record)
}

// partitionKey identifies one topic partition.
type partitionKey struct {
	topic     string
	partition int32
}

type orderEvent struct {
	OrderID     string `json:"order_id"`
	Customer    string `json:"customer"`
	SKU         string `json:"sku"`
	Quantity    int    `json:"quantity"`
	AmountCents int    `json:"amount_cents"`
	CreatedAt   string `json:"created_at"`
	S3Key       string `json:"s3_key"`
	Signature   string `json:"signature"`
}

type config struct {
	brokers []string
	topic   string
	group   string
	table   string
	region  string
	version string
	addr    string
}

func loadConfig() (config, error) {
	c := config{
		topic:   getenv("KAFKA_TOPIC", "orders"),
		group:   getenv("KAFKA_GROUP", "order-worker"),
		region:  getenv("AWS_DEFAULT_REGION", "us-east-1"),
		version: getenv("SERVICE_VERSION", "dev"),
		addr:    getenv("METRICS_ADDR", ":9090"),
	}
	brokers := os.Getenv("KAFKA_BROKERS")
	if brokers == "" {
		return c, errors.New("required environment variable KAFKA_BROKERS is not set")
	}
	c.brokers = strings.Split(brokers, ",")
	c.table = os.Getenv("DDB_TABLE")
	if c.table == "" {
		return c, errors.New("required environment variable DDB_TABLE is not set")
	}
	return c, nil
}

func getenv(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}

func main() {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelInfo}))
	slog.SetDefault(logger)

	if err := run(); err != nil {
		slog.Error("order-worker exiting", "err", err)
		os.Exit(1)
	}
}

func run() error {
	cfg, err := loadConfig()
	if err != nil {
		return fmt.Errorf("configuration error: %w", err)
	}

	// SIGTERM is what Kubernetes sends first on pod deletion. Handling it is the
	// difference between a graceful rolling update and dropped in-flight work.
	sigCtx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	// A fatal error in a background goroutine cancels the same context the
	// consume loop runs on, and context.Cause carries the reason back out to
	// main so the process exits non-zero instead of consuming forever.
	ctx, cancel := context.WithCancelCause(sigCtx)
	defer cancel(nil)

	// AWS_ENDPOINT_URL is honoured natively by aws-sdk-go-v2, so pointing at Floci
	// needs no code change at all — the same binary runs against real AWS.
	awsCfg, err := awsconfig.LoadDefaultConfig(ctx, awsconfig.WithRegion(cfg.region))
	if err != nil {
		return fmt.Errorf("load aws config: %w", err)
	}
	ddb := dynamodb.NewFromConfig(awsCfg)

	// blocked holds the partitions whose commit is pinned behind a record that
	// failed to write. It is read and written only between PollFetches and
	// AllowRebalance, and in the revoke callback, which BlockRebalanceOnPoll
	// documents as mutually exclusive — so it needs no lock.
	blocked := make(map[partitionKey]bool)

	// Commit strategy, per franz-go's group_committing example ("marks" style):
	//
	//   - AutoCommitMarks: autocommitting commits only records handed to
	//     MarkCommitRecords, so an offset is committed only after its DynamoDB
	//     write returned success.
	//   - BlockRebalanceOnPoll: a non-empty poll blocks rebalances until
	//     AllowRebalance, so a commit can never land on a partition this member
	//     has already lost.
	//   - OnPartitionsRevoked: flush marked offsets before losing partitions.
	//     franz-go calls this on group leave too, which is what makes
	//     client.Close() commit on SIGTERM.
	//
	// Autocommitting stays on, so a marked offset is checkpointed even if the
	// synchronous commit below fails. Delivery is at-least-once: a crash between
	// the DynamoDB write and the commit replays the record, and PutItem on the
	// same order_id is idempotent, so replay is harmless.
	client, err := kgo.NewClient(
		kgo.SeedBrokers(cfg.brokers...),
		kgo.ConsumerGroup(cfg.group),
		kgo.ConsumeTopics(cfg.topic),
		kgo.ConsumeResetOffset(kgo.NewOffset().AtStart()),
		kgo.AutoCommitMarks(),
		kgo.BlockRebalanceOnPoll(),
		kgo.OnPartitionsRevoked(func(revokeCtx context.Context, cl *kgo.Client, revoked map[string][]int32) {
			if err := cl.CommitMarkedOffsets(revokeCtx); err != nil {
				slog.Error("revoke commit failed", "err", err)
			}
			// A revoked partition starts clean if this member is assigned it
			// again: the next owner resumes from the offset just committed.
			for topic, partitions := range revoked {
				for _, p := range partitions {
					delete(blocked, partitionKey{topic: topic, partition: p})
				}
			}
		}),
		kgo.SessionTimeout(30*time.Second),
	)
	if err != nil {
		return fmt.Errorf("create kafka client: %w", err)
	}
	defer client.Close()

	var ready atomic.Bool
	go func() {
		if err := serveHTTP(ctx, cfg, &ready); err != nil {
			cancel(fmt.Errorf("metrics server: %w", err))
		}
	}()

	if err := client.Ping(ctx); err != nil {
		return fmt.Errorf("kafka not reachable: %w", err)
	}
	ready.Store(true)
	slog.Info("order-worker started", "version", cfg.version, "topic", cfg.topic, "table", cfg.table)

	for {
		fetches := client.PollFetches(ctx)
		if ctx.Err() != nil {
			if cause := context.Cause(ctx); !errors.Is(cause, context.Canceled) {
				return cause
			}
			slog.Info("shutting down")
			return nil
		}
		if errs := fetches.Errors(); len(errs) > 0 {
			for _, e := range errs {
				slog.Error("fetch error", "topic", e.Topic, "partition", e.Partition, "err", e.Err)
			}
			client.AllowRebalance()
			continue
		}

		fetches.EachPartition(func(p kgo.FetchTopicPartition) {
			processPartition(ctx, ddb, cfg.table, client, blocked, p)
		})

		// CommitMarkedOffsets commits the marks made above and nothing else.
		// It runs before AllowRebalance so the commit cannot cross a rebalance.
		if err := client.CommitMarkedOffsets(ctx); err != nil {
			slog.Error("commit failed", "err", err)
		}
		client.AllowRebalance()
	}
}

// processPartition writes one partition's records to DynamoDB in offset order
// and marks a record for commit only once its write has succeeded.
//
// A Kafka commit is a single per-partition offset, so marking any later offset
// would commit past every earlier one. The first failed write therefore blocks
// the partition: nothing at or after that offset is ever marked, the committed
// offset stays behind the failed record, and a restart replays from there.
// Blocking persists across polls because marks cannot rewind — a mark made on a
// later batch would commit the record that was never written.
func processPartition(ctx context.Context, ddb putItemAPI, table string, m recordMarker, blocked map[partitionKey]bool, p kgo.FetchTopicPartition) {
	key := partitionKey{topic: p.Topic, partition: p.Partition}
	if blocked[key] {
		return
	}
	for _, r := range p.Records {
		if err := handle(ctx, ddb, table, r); err != nil {
			processed.WithLabelValues("error").Inc()
			slog.Error("failed to process record", "topic", r.Topic, "partition", r.Partition, "offset", r.Offset, "err", err)
			blocked[key] = true
			return
		}
		processed.WithLabelValues("ok").Inc()
		m.MarkCommitRecords(r)
	}
}

func handle(ctx context.Context, ddb putItemAPI, table string, r *kgo.Record) error {
	start := time.Now()
	defer func() { processDuration.Observe(time.Since(start).Seconds()) }()

	var ev orderEvent
	if err := json.Unmarshal(r.Value, &ev); err != nil {
		// A malformed message will never become valid. Skipping it (rather than
		// retrying forever) keeps the partition moving. In production this record
		// goes to a dead-letter topic instead of the floor.
		slog.Warn("skipping malformed record", "offset", r.Offset, "err", err)
		return nil
	}

	if ts, err := time.Parse(time.RFC3339, ev.CreatedAt); err == nil {
		lag.Set(time.Since(ts).Seconds())
	}

	writeCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()

	_, err := ddb.PutItem(writeCtx, &dynamodb.PutItemInput{
		TableName: aws.String(table),
		Item: map[string]ddbtypes.AttributeValue{
			"order_id":     &ddbtypes.AttributeValueMemberS{Value: ev.OrderID},
			"customer":     &ddbtypes.AttributeValueMemberS{Value: ev.Customer},
			"sku":          &ddbtypes.AttributeValueMemberS{Value: ev.SKU},
			"quantity":     &ddbtypes.AttributeValueMemberN{Value: strconv.Itoa(ev.Quantity)},
			"amount_cents": &ddbtypes.AttributeValueMemberN{Value: strconv.Itoa(ev.AmountCents)},
			"created_at":   &ddbtypes.AttributeValueMemberS{Value: ev.CreatedAt},
			"s3_key":       &ddbtypes.AttributeValueMemberS{Value: ev.S3Key},
			"signature":    &ddbtypes.AttributeValueMemberS{Value: ev.Signature},
		},
	})
	if err != nil {
		return fmt.Errorf("put item order_id=%s: %w", ev.OrderID, err)
	}
	slog.Info("persisted order", "order_id", ev.OrderID, "offset", r.Offset)
	return nil
}

// serveHTTP runs the metrics and probe endpoints until ctx is cancelled. It
// returns nil on a clean shutdown and an error otherwise; failing to bind the
// metrics port is fatal to the process, not something to log and ignore.
func serveHTTP(ctx context.Context, cfg config, ready *atomic.Bool) error {
	mux := http.NewServeMux()
	mux.Handle("/metrics", promhttp.Handler())
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"status":"ok"}`))
	})
	mux.HandleFunc("/readyz", func(w http.ResponseWriter, _ *http.Request) {
		if !ready.Load() {
			w.WriteHeader(http.StatusServiceUnavailable)
			_, _ = w.Write([]byte(`{"status":"not-ready"}`))
			return
		}
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"status":"ready"}`))
	})

	srv := &http.Server{Addr: cfg.addr, Handler: mux, ReadHeaderTimeout: 5 * time.Second}
	go func() {
		<-ctx.Done()
		shutCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		_ = srv.Shutdown(shutCtx)
	}()
	if err := srv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
		return fmt.Errorf("listen on %s: %w", cfg.addr, err)
	}
	return nil
}
```

> **Why marks, and not “commit what succeeded”.** A Kafka commit is **one offset per
> partition**, not a set of offsets. So marking any later record commits past every earlier one,
> including a record whose DynamoDB write failed — marking only on success is necessary and not
> sufficient. The first failed write has to stop the partition dead, and it has to *stay* stopped
> across polls, because a mark made on the next batch would commit the record that was never
> written. That is what the `blocked` map buys.
>
> The three client options work as a set, and this is the shape franz-go documents — see
> [producing-and-consuming.md](https://github.com/twmb/franz-go/blob/master/docs/producing-and-consuming.md)
> on offset management, and the `goroutine_per_partition_consuming`
> [example](https://github.com/twmb/franz-go/tree/master/examples/goroutine_per_partition_consuming),
> whose third strategy is this pairing. `AutoCommitMarks` narrows autocommitting to marked records,
> `BlockRebalanceOnPoll` stops a commit landing on a partition this member has already lost, and
> `OnPartitionsRevoked` flushes marks before the partitions go. franz-go calls the revoke hook on
> group leave as well, which is what makes `client.Close()` commit on SIGTERM — and what
> `terminationGracePeriodSeconds: 45` in §10.1 exists to allow time for.

> **`run() error`, not a `main` full of `os.Exit(1)`.** `os.Exit` skips every deferred call, so a
> `main` that exits inline never runs `client.Close()` and never commits. Pushing the work into
> `run()` means one exit point, after the defers. The metrics server gets the same treatment through
> `context.WithCancelCause`: a failure to bind `:9090` cancels the consume loop and the cause carries
> the reason out to `main`, instead of being logged by a goroutine nobody is watching while the pod
> stays happily ready.

**`services/order-worker/main_test.go`**

```go
package main

import (
	"os"
	"testing"
)

func TestLoadConfigRequiresBrokers(t *testing.T) {
	os.Clearenv()
	if _, err := loadConfig(); err == nil {
		t.Fatal("expected an error when KAFKA_BROKERS is unset")
	}
}

func TestLoadConfigDefaults(t *testing.T) {
	os.Clearenv()
	t.Setenv("KAFKA_BROKERS", "a:9092,b:9092")
	t.Setenv("DDB_TABLE", "orders")

	cfg, err := loadConfig()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(cfg.brokers) != 2 {
		t.Fatalf("expected 2 brokers, got %d", len(cfg.brokers))
	}
	if cfg.topic != "orders" {
		t.Fatalf("expected default topic 'orders', got %q", cfg.topic)
	}
	if cfg.group != "order-worker" {
		t.Fatalf("expected default group 'order-worker', got %q", cfg.group)
	}
}
```

Config tests are cheap and prove little. The commit boundary is the part of this service that can
lose data silently, so it gets tests that fail if anyone reintroduces the naive version. `handle` and
`processPartition` take the two narrow interfaces declared at the top of `main.go` — `putItemAPI` and
`recordMarker` — which is the whole reason a fake can drive a failing write.

**`services/order-worker/main_test.go`**

```go
var errWriteFailed = errors.New("dynamodb is having a day")

// fakeDDB records every PutItem it is asked to make and fails the ones whose
// order_id is listed in failOn.
type fakeDDB struct {
	failOn map[string]bool
	puts   []string
}

func (f *fakeDDB) PutItem(_ context.Context, params *dynamodb.PutItemInput, _ ...func(*dynamodb.Options)) (*dynamodb.PutItemOutput, error) {
	id := params.Item["order_id"].(*ddbtypes.AttributeValueMemberS).Value
	f.puts = append(f.puts, id)
	if f.failOn[id] {
		return nil, errWriteFailed
	}
	return &dynamodb.PutItemOutput{}, nil
}

// fakeMarker records the offsets handed to MarkCommitRecords. Those offsets are
// exactly what franz-go would commit, so asserting on them asserts on the
// commit boundary.
type fakeMarker struct{ marked []int64 }

func (m *fakeMarker) MarkCommitRecords(rs ...*kgo.Record) {
	for _, r := range rs {
		m.marked = append(m.marked, r.Offset)
	}
}

// partitionOf builds a one-partition fetch result holding one record per
// order_id, at consecutive offsets starting from 0.
func partitionOf(orderIDs ...string) kgo.FetchTopicPartition {
	p := kgo.FetchTopicPartition{Topic: "orders"}
	p.Partition = 3
	for i, id := range orderIDs {
		p.Records = append(p.Records, &kgo.Record{
			Topic:     "orders",
			Partition: 3,
			Offset:    int64(i),
			Value:     []byte(`{"order_id":"` + id + `","quantity":1,"amount_cents":100}`),
		})
	}
	return p
}

// ...

// This is the regression test for the commit semantics: a failed DynamoDB write
// must stop the commit boundary dead. If someone reintroduces marking (and so
// committing) records at or past a failed offset, this fails.
func TestProcessPartitionNeverMarksAtOrPastAFailedWrite(t *testing.T) {
	ddb := &fakeDDB{failOn: map[string]bool{"b": true}}
	m := &fakeMarker{}
	blocked := map[partitionKey]bool{}
	key := partitionKey{topic: "orders", partition: 3}

	processPartition(context.Background(), ddb, "orders", m, blocked, partitionOf("a", "b", "c"))

	if !equalOffsets(m.marked, []int64{0}) {
		t.Fatalf("only offset 0 was written successfully, but offsets %v were marked for commit", m.marked)
	}
	if !blocked[key] {
		t.Fatal("expected the partition to be blocked after a failed write")
	}
}

// Marks cannot rewind, so once a partition is blocked a later batch must not
// mark it either — that would commit past the record that was never written.
func TestProcessPartitionStaysBlockedOnLaterBatches(t *testing.T) {
	ddb := &fakeDDB{failOn: map[string]bool{"a": true}}
	m := &fakeMarker{}
	blocked := map[partitionKey]bool{}

	processPartition(context.Background(), ddb, "orders", m, blocked, partitionOf("a"))
	if len(m.marked) != 0 {
		t.Fatalf("expected nothing marked, got %v", m.marked)
	}

	ddb.failOn = nil
	processPartition(context.Background(), ddb, "orders", m, blocked, partitionOf("d", "e"))

	if len(m.marked) != 0 {
		t.Fatalf("a blocked partition must not be marked on a later batch, got %v", m.marked)
	}
	if len(ddb.puts) != 1 {
		t.Fatalf("a blocked partition must not be written again, got puts %v", ddb.puts)
	}
}
```

The repo file carries three more: the happy path (`equalOffsets(m.marked, []int64{0, 1, 2})`), one
that a malformed record is still marked — otherwise one bad message pins the partition's commit
forever — and one that `handle` wraps the `PutItem` error with the `order_id`. The imports and the
`equalOffsets` helper are there too.

> **At-least-once vs exactly-once.** An offset is marked, and so committed, only *after* the DynamoDB write returns success. A crash in between replays the record. Because `PutItem` with the same `order_id` overwrites rather than duplicates, replay is a no-op — the write is idempotent, so at-least-once delivery gives us effectively-once *results*. Exactly-once across Kafka and DynamoDB would need transactional coordination the two systems don't share. **The general lesson: don't buy exactly-once delivery; make your writes idempotent and buy at-least-once, which is cheap.**

**`services/order-worker/Dockerfile`**

```dockerfile
# syntax=docker/dockerfile:1.7
FROM docker.io/library/golang:1.26-alpine AS builder
WORKDIR /src

COPY go.mod go.sum ./
RUN --mount=type=cache,target=/go/pkg/mod go mod download

COPY . .
# CGO_ENABLED=0 → a static binary, which is the only kind that runs on
# distroless/static. -trimpath and -s -w strip build paths and debug info for a
# smaller, more reproducible artifact.
RUN --mount=type=cache,target=/go/pkg/mod \
    --mount=type=cache,target=/root/.cache/go-build \
    CGO_ENABLED=0 GOOS=linux go build \
      -trimpath \
      -ldflags="-s -w" \
      -o /out/order-worker .


FROM gcr.io/distroless/static-debian12:nonroot
# --chmod=0755, not a bare COPY. Once the binary is built outside this Dockerfile
# and shipped in as a CI artifact (Phase 3), the executable bit does not survive
# the transfer, and the pod fails at `exec: "/order-worker": permission denied`
# with no application output at all. Setting it here is correct either way.
COPY --chmod=0755 --from=builder /out/order-worker /order-worker
USER 65532:65532
EXPOSE 9090
ENTRYPOINT ["/order-worker"]
```

> [!warning] **Fully qualify every `FROM`.**
> `docker.io/library/golang:1.26-alpine`, never `golang:1.26-alpine`. Docker assumes Docker Hub for a
> short name; Buildah — which [§12.5](phase-3-delivery.md#125-the-pipeline) builds with — runs
> `short-name-mode = "enforcing"` and refuses to guess, so an unqualified name that works on your
> laptop stalls or fails in CI. Pinning the registry is the same discipline as pinning the tag.

> **Tradeoff — distroless vs alpine vs scratch.** Distroless static gives you a non-root user, CA certificates and timezone data, and nothing else — no shell, no package manager, so `kubectl exec` into it is impossible. That's the point: it's a ~2 MB attack surface. The cost is real, though — when something breaks in production you cannot shell in, and you must debug via `kubectl debug --image=busybox` ephemeral containers instead. Alpine keeps a shell at the price of a package manager and musl libc quirks. For a compiled static Go binary, distroless is the right default.

Build and test locally:

```bash
cd services/order-worker
go mod tidy
go vet ./...
go test ./...
cd ../..
```

### 3.3 Commit and push

```bash
git add .
git commit -m "feat: order-api and order-worker services"
git push -u origin main
```

---

## 6. Floci: AWS without AWS

### 6.1 Why an emulator at all

Your app talks to S3 and DynamoDB. You have three options for local development:

| Option | Cost | Fidelity | Verdict |
|---|---|---|---|
| Real AWS | money, credentials on laptops, shared-state collisions | perfect | wrong for a dev inner loop |
| Hand-rolled fakes (in-process mocks) | free | poor — you test your mock, not the SDK | fine for unit tests, useless for integration |
| Emulator (Floci) | free | high — real AWS wire protocol | right |

Floci serves the actual AWS protocol on port 4566, so the AWS SDK, `aws` CLI, IAM signing and pagination all behave normally. Your application code contains **zero** emulator-specific branches — the only difference between local and production is the value of `AWS_ENDPOINT_URL`, which both `boto3` and `aws-sdk-go-v2` honour natively.

> **Why Floci and not LocalStack.** The emulator you will be handed at work is **LocalStack Pro**, and it is the incumbent by a wide margin. We cannot use it here. LocalStack's Community edition sunset in March 2026: basic usage now requires an auth token and the last community release is frozen with no security updates. What replaced it is a free **Hobby** tier that is non-commercial-only and still needs an account, and paid tiers at **$39–89 per developer per month** (as of 2026-08) — a per-seat gate on a tutorial anyone should be able to run offline.
>
> Floci is the open-source stand-in: MIT-licensed, no account, no telemetry, ~69 AWS services, and a drop-in replacement down to serving LocalStack's own `/_localstack/health` endpoint, so existing tooling and Testcontainers wait strategies keep working. Repo: <https://github.com/floci-io/floci>.
>
> **What actually transfers is not Floci.** It is the AWS wire protocol: SigV4-signed requests, `boto3` and `aws-sdk-go-v2` behaviour, pagination, path-style S3 addressing, and the fact that pointing an SDK at an emulator is one environment variable (`AWS_ENDPOINT_URL`) rather than a code branch. Swap Floci for LocalStack Pro on Monday and the only thing that changes is the image name and the auth token. That is the point of choosing an emulator that speaks the real protocol instead of a mock.
>
> **Where it stops being equivalent, stated plainly.** Floci is new — the repo dates from February 2026 — so it has no long track record, and you should expect to meet LocalStack rather than Floci in any real job. LocalStack Pro also emulates things the free tiers of anything do not, notably **IAM policy evaluation**; here, credentials are accepted and never authorised, so nothing in this tutorial teaches you whether your IAM policy is correct. More generally, an emulator is not AWS: IAM semantics, consistency and throttling all differ. It is good enough to build against and not good enough to certify against.

### 6.2 Deploy Floci into the cluster

**`deploy/platform/floci.yaml`**

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: floci
  labels:
    # Mesh enrolment belongs in git, not in a `kubectl label` you run once.
    # Argo CD recreates this Namespace on any teardown, and an imperative
    # label does not come back with it: pods return as 1/1 with no sidecar,
    # STRICT mTLS rejects them and the PodMonitor matches nothing.
    istio-injection: enabled
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: floci
  namespace: floci
  labels: { app.kubernetes.io/name: floci }
spec:
  replicas: 1
  strategy: { type: Recreate }   # single writer; never run two with shared storage
  selector:
    matchLabels: { app.kubernetes.io/name: floci }
  template:
    metadata:
      labels: { app.kubernetes.io/name: floci }
    spec:
      # The `floci` Service is in this namespace, so kubelet would inject
      # FLOCI_PORT=tcp://<clusterIP>:4566. Floci is a Quarkus app and SmallRye
      # Config reads that as the `floci.port` property, which must be an integer.
      # Startup then fails on the injected value. Turn the injection off.
      enableServiceLinks: false
      containers:
        - name: floci
          image: floci/floci:1.5.11
          ports:
            - { name: aws, containerPort: 4566 }
          env:
            # Required when Floci is behind a DNS name other than localhost, so
            # generated endpoints (e.g. S3 virtual-host URLs, SQS queue URLs)
            # point back at something callers can reach.
            - { name: FLOCI_HOSTNAME,           value: "floci.floci.svc.cluster.local" }
            - { name: FLOCI_DEFAULT_REGION,     value: "us-east-1" }
            - { name: FLOCI_DEFAULT_ACCOUNT_ID, value: "000000000000" }
            - { name: FLOCI_STORAGE_MODE,       value: "memory" }
          readinessProbe:
            httpGet: { path: /_localstack/health, port: aws }
            initialDelaySeconds: 2
            periodSeconds: 5
          livenessProbe:
            httpGet: { path: /_localstack/health, port: aws }
            initialDelaySeconds: 10
            periodSeconds: 15
          resources:
            requests: { cpu: 100m, memory: 128Mi }
            limits:   { memory: 1Gi }
---
apiVersion: v1
kind: Service
metadata:
  name: floci
  namespace: floci
spec:
  selector: { app.kubernetes.io/name: floci }
  ports:
    - { name: aws, port: 4566, targetPort: aws }
```

> **`FLOCI_STORAGE_MODE: memory`.** State vanishes on restart, which is correct for a disposable dev environment — every run starts clean and you never debug stale fixtures. Set `persistent` (plus `FLOCI_STORAGE_PERSISTENT_PATH` and a PVC) when you want data to survive; `wal` adds write-ahead logging for crash consistency. Choosing `memory` here also means the bootstrap Job in §6.3 must be re-runnable, which is a property you want anyway.

Apply it:

```bash
kubectl apply -f deploy/platform/floci.yaml
kubectl -n floci rollout status deployment/floci --timeout=120s
```

### 6.3 Bootstrap the S3 bucket and DynamoDB table

Resources have to exist before the app starts. In production this is Terraform or CloudFormation. Here it's a Kubernetes Job, which is the honest local equivalent: declarative, re-runnable, and versioned in git.

**`deploy/platform/floci-bootstrap.yaml`**

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: floci-bootstrap
  namespace: floci
spec:
  backoffLimit: 6
  ttlSecondsAfterFinished: 600
  template:
    metadata:
      annotations:
        # Once §9 enrolls this namespace in the mesh, an injected sidecar would
        # keep this pod alive after the job finishes, so it never completes.
        # Harmless before Istio exists; required after.
        sidecar.istio.io/inject: "false"
    spec:
      restartPolicy: OnFailure
      containers:
        - name: awscli
          image: amazon/aws-cli:2.32.9
          env:
            - { name: AWS_ENDPOINT_URL,      value: "http://floci.floci.svc.cluster.local:4566" }
            - { name: AWS_DEFAULT_REGION,    value: "us-east-1" }
            # Floci does not validate credentials, but the SDK refuses to sign
            # without them, so any non-empty value works.
            - { name: AWS_ACCESS_KEY_ID,     value: "test" }
            - { name: AWS_SECRET_ACCESS_KEY, value: "test" }
          command: ["/bin/sh", "-c"]
          args:
            - |
              set -eu

              echo "waiting for floci..."
              until aws s3 ls >/dev/null 2>&1; do sleep 2; done

              echo "creating bucket orders-raw (idempotent)"
              aws s3api create-bucket --bucket orders-raw 2>/dev/null || true

              echo "creating table orders (idempotent)"
              aws dynamodb create-table \
                --table-name orders \
                --attribute-definitions AttributeName=order_id,AttributeType=S \
                --key-schema AttributeName=order_id,KeyType=HASH \
                --billing-mode PAY_PER_REQUEST 2>/dev/null || true

              aws dynamodb wait table-exists --table-name orders

              echo "--- result ---"
              aws s3 ls
              aws dynamodb list-tables
```

```bash
kubectl apply -f deploy/platform/floci-bootstrap.yaml
kubectl -n floci wait --for=condition=complete job/floci-bootstrap --timeout=180s
kubectl -n floci logs job/floci-bootstrap
```

You should see `orders-raw` and `{"TableNames": ["orders"]}`.

> **Why `|| true` on create.** The Job may be re-run (Floci restarts, `memory` storage, empty state — or Argo CD re-applies it). `create-bucket` on an existing bucket returns an error; swallowing it makes the Job idempotent. The `wait table-exists` afterwards is what actually asserts the desired end state, which is the right way round: **assert the outcome, tolerate the mechanism.**

### 6.4 Reaching Floci from your laptop

Useful for poking at state while debugging:

```bash
kubectl -n floci port-forward svc/floci 4566:4566 &

export AWS_ENDPOINT_URL=http://localhost:4566
export AWS_DEFAULT_REGION=us-east-1
export AWS_ACCESS_KEY_ID=test
export AWS_SECRET_ACCESS_KEY=test

aws s3 ls
aws dynamodb scan --table-name orders
```

Kill the forward with `kill %1` when done.

> **This stops working in [§9.4](phase-4-service-mesh.md#94-mtls-and-proving-it-is-actually-on), and that is the correct behaviour.** `port-forward` delivers plaintext to the pod from outside the mesh, which is exactly what STRICT mTLS exists to refuse — you'll get `Connection reset by peer`, from a command that worked yesterday, with nothing in the application logs. The replacement is to run the client *inside* the mesh instead of tunnelling into it:
>
> ```bash
> kubectl -n floci run awscli --rm -it --restart=Never --image=amazon/aws-cli:2.32.9 \
>   --env AWS_ENDPOINT_URL=http://floci.floci.svc.cluster.local:4566 \
>   --env AWS_DEFAULT_REGION=us-east-1 \
>   --env AWS_ACCESS_KEY_ID=test --env AWS_SECRET_ACCESS_KEY=test \
>   -- s3 ls s3://orders-raw/ --recursive
> ```
>
> That pod gets a sidecar, so it speaks mTLS and satisfies the authorization policy in §9.5 — assuming you added its ServiceAccount, which by default you did not. If it's denied, that's the policy working. Debugging a zero-trust network from outside it is supposed to be hard; the fix is to bring your tools inside, not to poke holes.

---

## 7. OpenBao and External Secrets

### 7.1 The problem with Kubernetes Secrets

A Kubernetes `Secret` is base64-encoded, not encrypted. Anyone with `get secret` in a namespace reads it in plaintext, and if you commit one to git you've published it. That leaves you three bad options and one good one:

| Approach | Problem |
|---|---|
| Secrets in git, plain | Catastrophic. |
| Secrets in git, sealed/encrypted (SOPS, Sealed Secrets) | Works, but rotation means a git commit and a deploy, and revocation is impossible — the old ciphertext is in history forever. |
| Secrets injected by CI | CI now holds every production secret. Your build system becomes the highest-value target in the company. |
| **Secrets in a vault, pulled by the cluster** | Rotation is a vault operation with no deploy. Access is audited per-identity. CI never sees them. |

We take the last one: **OpenBao** stores the secrets, **External Secrets Operator (ESO)** projects them into Kubernetes `Secret` objects that pods consume normally.

> **Why OpenBao rather than HashiCorp Vault.** The secrets manager you will be handed at work is **Vault** — most likely Vault Enterprise, which is quote-only and routinely a five- or six-figure annual contract. Vault also moved to the Business Source License in 2023, so it is no longer open source in any sense a tutorial can rely on. OpenBao is the Linux Foundation fork of the last Mozilla-Public-License version, under open governance, and **API-compatible**.
>
> Be precise about what "transfers" means, because it is more than a hand-wave: paths, ACL policy documents, the KV v2 engine and its `/data/` and `/metadata/` split, the Kubernetes auth method and its TokenReview dependency, tokens and leases, and the `bao`/`vault` CLI verbs are the same on both. So is the ecosystem — which is the concrete proof: ESO configures OpenBao using its **`vault` provider**. There is no separate `openbao` provider key, and expecting one is the single most common mistake here. Everything you type in §7 you can type at a Vault cluster.
>
> **Where it stops being equivalent.** Vault *Community* Edition is free to run, so "we picked OpenBao because Vault costs money" would be a lie — the licence is the gate, not the invoice. The invoice appears one level up, and that is the real gap: Sentinel policy-as-code, performance and disaster-recovery replication, HSM auto-unseal and seal wrapping, and control groups are Vault **Enterprise** features, and this tutorial teaches none of them because neither Vault CE nor OpenBao has them. Namespaces are the partial exception — OpenBao shipped its own, API-compatible with Vault Enterprise's, in 2.3 (beta, May 2025) — but they are not storage- or operator-API-compatible, so a migration is not a copy. Assume the *application-facing* API matches and verify anything operator-facing against OpenBao's own docs rather than Vault's.

### 7.2 Install OpenBao

```bash
helm repo add openbao https://openbao.github.io/openbao-helm
helm repo update

helm upgrade --install openbao openbao/openbao \
  --version 0.29.1 \
  --namespace openbao --create-namespace \
  --set server.dev.enabled=true \
  --set server.dev.devRootToken=root \
  --set injector.enabled=false \
  --wait

kubectl -n openbao get pods
```

You should see `openbao-0` Running.

> **Dev mode is a loaded gun. Here is exactly what you're accepting:** in-memory storage (everything is lost on restart), auto-unsealed at boot (the unseal key is not protected), TLS disabled (tokens cross the network in the clear), and a root token you just typed into your shell history. Production is the opposite of all four: integrated Raft storage on persistent volumes, auto-unseal backed by a KMS/HSM, end-to-end TLS, and no long-lived root token — you generate one with unseal-key quorum, use it, and revoke it. Dev mode exists so you can learn the *data model* without also learning the *operations model* on day one.

> We disable the **agent injector** (`injector.enabled=false`) because we're using ESO instead. The injector is the other valid pattern: a mutating webhook adds a sidecar that writes secrets to a shared volume as files. Sidecar injection gives you live secret rotation without a pod restart and never creates a Kubernetes `Secret` object at all — strictly better isolation. ESO's advantage is that the result is an ordinary `Secret`, so *anything* consumes it (image pull secrets, TLS certs for Ingress, third-party charts that only accept a secret name). We need exactly that in §7.6. Pick the injector when your app can read files and you want zero secrets in etcd; pick ESO when you need interoperability.

### 7.3 Put secrets in OpenBao

Everything below runs the `bao` CLI inside the pod, so nothing is installed on your laptop.

This is bootstrap, and it runs as root because enabling a secrets engine is a mount operation on `sys/mounts` that no scoped policy grants. [§7.5a](#75a-give-humans-an-auth-method-too) builds the non-root path that everything after §7 uses.

```bash
BAO="kubectl -n openbao exec -i openbao-0 -- env BAO_TOKEN=root BAO_ADDR=http://127.0.0.1:8200 bao"

# KV v2 at the mount point "shop". v2 gives you versioning and soft-delete;
# v1 is a flat overwrite with no history. Always choose v2 for application config.
$BAO secrets enable -path=shop -version=2 kv

# The HMAC key order-api signs payloads with.
$BAO kv put shop/order-api \
  signing_key="$(openssl rand -hex 32)"

# Nexus pull credentials, so Kubernetes can pull our private images.
$BAO kv put shop/nexus \
  username=ci \
  password=ci-password-change-me

# Verify
$BAO kv get shop/order-api
$BAO kv get shop/nexus
```

> **Note the path shape: `shop/<app>`.** Path *is* the authorization boundary in OpenBao — policies are written against path globs. Structuring paths as `<namespace>/<app>` means the policy "order-api may read `shop/order-api/*` and nothing else" is one line. If you flatten everything into `secret/`, every policy becomes an enumeration of individual keys and it rots immediately. **Design your secret paths before you write your first policy.**

### 7.4 Configure Kubernetes authentication

We want pods to authenticate to OpenBao using their Kubernetes ServiceAccount identity — no static token to distribute, rotate, or leak.

The mechanism: a pod presents its projected ServiceAccount JWT; OpenBao calls the Kubernetes `TokenReview` API to verify it; if it matches a configured role, OpenBao issues a short-lived token with the mapped policies.

For OpenBao to call `TokenReview`, its own ServiceAccount needs the `system:auth-delegator` ClusterRole:

```bash
kubectl create clusterrolebinding openbao-token-review \
  --clusterrole=system:auth-delegator \
  --serviceaccount=openbao:openbao
```

Now enable and configure the auth method. This is bootstrap again — `auth enable` and `auth/kubernetes/config` are `sys/auth` and `auth/*` writes, which the operator policy in [§7.5a](#75a-give-humans-an-auth-method-too) deliberately does not grant. Note what is **not** in this command:

```bash
kubectl -n openbao exec -i openbao-0 -- sh -c '
set -eu
export BAO_TOKEN=root BAO_ADDR=http://127.0.0.1:8200

bao auth enable kubernetes 2>/dev/null || true

bao write auth/kubernetes/config \
  kubernetes_host="https://${KUBERNETES_SERVICE_HOST}:${KUBERNETES_SERVICE_PORT}"

echo "kubernetes auth configured"
'
```

There is no `token_reviewer_jwt` and no `kubernetes_ca_cert`, and omitting them is the
documented configuration for an OpenBao running inside the cluster it authenticates against.
When those fields are absent, OpenBao reads the token and CA from its own service account
mount **on every request**, and re-reads them as they change.

Passing them explicitly looks more careful and is the opposite. Since Kubernetes 1.21 the
projected service account token is bound and short-lived — roughly an hour, rotated
automatically at about 80% of its life. `token_reviewer_jwt="$(cat $SA/token)"` copies the
*contents* of that token into OpenBao's config and freezes a snapshot of it. Everything works.
Then, an hour or so later, every TokenReview call OpenBao makes starts failing `permission
denied`, the `ClusterSecretStore` flips to `Invalid`, and every `ExternalSecret` in the cluster
stops refreshing — long after the setup you verified as green. The same argument applies to
`kubernetes_ca_cert`, which breaks on CA rotation instead of token rotation.

Write a policy granting read-only access to the `shop` mount, and a role binding it to the ESO ServiceAccount. Still bootstrap: writing a policy is `sys/policies/acl/*`, and an identity that can write policies can grant itself anything, which is why nothing but root gets it here.

```bash
kubectl -n openbao exec -i openbao-0 -- sh -c '
set -eu
export BAO_TOKEN=root BAO_ADDR=http://127.0.0.1:8200

# KV v2 stores data under <mount>/data/<path>; metadata lives at <mount>/metadata/<path>.
# Forgetting the /data/ segment is the second most common mistake with KV v2.
bao policy write shop-read - <<EOF
path "shop/data/*" {
  capabilities = ["read"]
}
path "shop/metadata/*" {
  capabilities = ["read", "list"]
}
EOF

bao write auth/kubernetes/role/eso \
  bound_service_account_names=external-secrets \
  bound_service_account_namespaces=external-secrets \
  policies=shop-read \
  ttl=1h

echo "policy and role created"
'
```

> **Least privilege, concretely.** The `shop-read` policy grants `read` and nothing else — ESO cannot write, delete, or list secret *values*. The role is bound to one ServiceAccount in one namespace, so a compromised pod in another namespace cannot assume it. `ttl=1h` means a stolen token expires within the hour. Those three constraints — capability, identity binding, lifetime — are the whole of secrets access control. Every vault does it the same way.

### 7.5 Install External Secrets Operator

```bash
helm repo add external-secrets https://charts.external-secrets.io
helm repo update

helm upgrade --install external-secrets external-secrets/external-secrets \
  --version 2.6.0 \
  --namespace external-secrets --create-namespace \
  --set installCRDs=true \
  --wait

kubectl -n external-secrets get pods
```

Three pods: the controller, the webhook, and the cert-controller.

Now create the namespace our app lives in, and a `ClusterSecretStore` pointing at OpenBao:

**`deploy/platform/secret-store.yaml`**

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: shop
  labels:
    # Mesh enrolment belongs in git, not in a `kubectl label` you run once.
    # Argo CD recreates this Namespace on any teardown, and an imperative
    # label does not come back with it: pods return as 1/1 with no sidecar,
    # STRICT mTLS rejects them and the PodMonitor matches nothing.
    istio-injection: enabled
---
apiVersion: external-secrets.io/v1
kind: ClusterSecretStore
metadata:
  name: openbao
spec:
  provider:
    # OpenBao is API-compatible with Vault, so ESO drives it through the
    # `vault` provider. There is no `openbao:` key — this is correct, not a typo.
    vault:
      server: "http://openbao.openbao.svc.cluster.local:8200"
      path: "shop"      # the KV mount point
      version: "v2"
      auth:
        kubernetes:
          mountPath: "kubernetes"
          role: "eso"
          serviceAccountRef:
            name: external-secrets
            namespace: external-secrets
```

```bash
kubectl apply -f deploy/platform/secret-store.yaml
kubectl get clustersecretstore openbao -o jsonpath='{.status.conditions[0]}' && echo
# {"message":"store validated","reason":"Valid","status":"True","type":"Ready"}
```

If it says `Invalid`, check `kubectl -n external-secrets logs deploy/external-secrets` — 99% of the time it's the `system:auth-delegator` binding or a typo in the role name.

> **`ClusterSecretStore` vs `SecretStore`.** A `SecretStore` is namespaced: teams configure their own vault connection and can't reach each other's. A `ClusterSecretStore` is one shared definition — less duplication, but any namespace can reference it, so your isolation now depends entirely on the OpenBao policy rather than on Kubernetes RBAC. We use `ClusterSecretStore` because we have one team; use namespaced stores the moment you have two.

### 7.5a Give humans an auth method too

The machine path is finished and it is genuinely least-privilege: ESO presents a ServiceAccount JWT, gets a token carrying `shop-read`, and that token can read the `shop` mount and do nothing else. The human path has been the root token the entire time. Every `$BAO` command above ran as root.

OpenBao documents the `root` policy as being for initial setup and emergencies, to be revoked once a real auth method exists ([tokens](https://openbao.org/docs/concepts/tokens/)). Bootstrapping that first non-root path is itself a root operation — there is no way around it, and it is the last thing root should be used for.

Enable `userpass`, write a policy scoped to the `shop` mount, and bind a user to it:

```bash
kubectl -n openbao exec -i openbao-0 -- sh -c '
set -eu
export BAO_TOKEN=root BAO_ADDR=http://127.0.0.1:8200   # bootstrap, and the last of it

bao auth enable userpass 2>/dev/null || true

# Least privilege for an operator of THIS platform: write the secrets the
# platform consumes, and see what is there. Not the root policy under another
# name — no sys/*, no auth/*, no mount management, no delete or destroy, and no
# ability to widen its own grant.
bao policy write shop-admin - <<EOF
path "shop/data/*" {
  capabilities = ["create", "update", "read"]
}
path "shop/metadata/*" {
  capabilities = ["read", "list"]
}
EOF

bao write auth/userpass/users/operator \
  password="change-me" \
  token_policies=shop-admin \
  token_ttl=1h \
  token_max_ttl=8h
'
```

Now log in as a human and keep the token it hands back:

```bash
kubectl -n openbao exec -it openbao-0 -- env BAO_ADDR=http://127.0.0.1:8200 \
  bao login -method=userpass username=operator
# prompts for the password, then prints the token, its 1h duration,
# and its policies: default and shop-admin

BAO_OP="kubectl -n openbao exec -i openbao-0 -- env BAO_TOKEN=<the token above> BAO_ADDR=http://127.0.0.1:8200 bao"
```

Prove the grant in both directions. It is not a real boundary until you have seen it refuse something:

```bash
# Allowed: writing a secret the platform consumes.
$BAO_OP kv put shop/order-api signing_key="$(openssl rand -hex 32)"

# Refused: everything else.
$BAO_OP auth list
```

```
Error listing enabled authentications: Error making API request.
URL: GET http://127.0.0.1:8200/v1/sys/auth
Code: 403. Errors:
* 1 error occurred:
	* permission denied
```

That 403 is the point of the section. The operator can rotate every credential on this platform and cannot enable an auth method, mount an engine, read a policy, or grant itself anything.

> **`bao kv patch` needs a separate `patch` capability, and it is deliberately not granted.** Every `kv put` in this tutorial is a full overwrite of the version: `kv put shop/backstage github_token=...` on a path that also holds `postgres_password` destroys the other keys. Write every key of a path in one command, and read the path first if you are unsure what is on it.

The same three steps are packaged as a re-runnable Job, because dev-mode OpenBao loses everything on restart and you will need them again:

**`deploy/platform/openbao-operator-auth.yaml`**

```yaml
# The human path into OpenBao.
#
# The machine path already exists: ESO authenticates with its ServiceAccount
# through the kubernetes auth method and gets the read-only `shop-read` policy.
# Humans have had nothing, so every operator write has been made with the root
# token. The root policy is meant for initial setup and emergencies only and
# should be revoked once a real auth method exists
# (https://openbao.org/docs/concepts/tokens). This Job builds that auth method:
# `userpass`, a scoped `shop-admin` policy, and an `operator` user bound to it.
#
# Bootstrapping an auth method is itself a root operation — there is no way to
# create the first non-root path without a root token. That token is supplied at
# run time out of a Secret rather than committed here:
#
#   kubectl -n openbao create secret generic openbao-bootstrap \
#     --from-literal=root-token=root \
#     --from-literal=operator-password=<choose one> \
#     --dry-run=client -o yaml | kubectl apply -f -
#
# A Job's pod template is immutable once created, so re-running this is
# `kubectl delete -f` then `kubectl apply -f`. The script itself is idempotent:
# enabling an already-enabled auth method and rewriting an existing policy or
# user are all no-ops.
apiVersion: batch/v1
kind: Job
metadata:
  name: openbao-operator-auth
  namespace: openbao
spec:
  backoffLimit: 6
  ttlSecondsAfterFinished: 600
  template:
    metadata:
      annotations:
        # An injected sidecar keeps the pod alive after the job finishes, so it
        # never completes.
        sidecar.istio.io/inject: "false"
    spec:
      restartPolicy: OnFailure
      containers:
        - name: bao
          image: quay.io/openbao/openbao:2.6.1
          env:
            - { name: BAO_ADDR, value: "http://openbao.openbao.svc.cluster.local:8200" }
            - name: BAO_TOKEN
              valueFrom:
                secretKeyRef: { name: openbao-bootstrap, key: root-token }
            - name: OPERATOR_PASSWORD
              valueFrom:
                secretKeyRef: { name: openbao-bootstrap, key: operator-password }
          command: ["/bin/sh", "-c"]
          args:
            - |
              set -eu

              echo "waiting for openbao..."
              until bao status >/dev/null 2>&1; do sleep 2; done

              echo "enabling userpass (idempotent)"
              bao auth enable userpass 2>/dev/null || true

              # Least privilege for an operator of THIS platform: write the
              # secrets the platform consumes, and see what is there. Not the
              # root policy with a different name — no sys/*, no auth/*, no
              # mount management, no ability to widen its own grant, and no
              # delete or destroy on secret data.
              echo "writing shop-admin policy"
              bao policy write shop-admin - <<'POLICY'
              path "shop/data/*" {
                capabilities = ["create", "update", "read"]
              }
              path "shop/metadata/*" {
                capabilities = ["read", "list"]
              }
              POLICY

              echo "binding operator user to shop-admin"
              bao write auth/userpass/users/operator \
                password="$OPERATOR_PASSWORD" \
                token_policies=shop-admin \
                token_ttl=1h \
                token_max_ttl=8h

              echo "--- result ---"
              bao auth list
              bao policy read shop-admin
```

```bash
kubectl -n openbao create secret generic openbao-bootstrap \
  --from-literal=root-token=root \
  --from-literal=operator-password=change-me \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl apply -f deploy/platform/openbao-operator-auth.yaml
kubectl -n openbao logs job/openbao-operator-auth -f
```

> **The root token is not revoked here, and cannot be.** This cluster runs OpenBao in dev mode, where the root token is a fixed value passed at startup and recreated every time the pod restarts — revoking it accomplishes nothing. In a real cluster the last step of this section is `bao token revoke <root-token>`, after which a new root token exists only if you run `bao operator generate-root` with a quorum of unseal-key holders. That quorum requirement is the whole design: root is an event several people have to agree to, not a string in someone's shell history.

### 7.6 Let Kubernetes pull from Nexus

This is where the ESO choice pays off: we generate a `kubernetes.io/dockerconfigjson` Secret from vault data, using a template.

**`deploy/platform/external-secrets.yaml`**

```yaml
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: nexus-pull
  namespace: shop
spec:
  refreshInterval: "1h"
  secretStoreRef:
    name: openbao
    kind: ClusterSecretStore
  target:
    name: nexus-pull
    creationPolicy: Owner
    template:
      type: kubernetes.io/dockerconfigjson
      data:
        .dockerconfigjson: |
          {
            "auths": {
              "nexus:8082": {
                "username": "{{ .username }}",
                "password": "{{ .password }}",
                "auth": "{{ printf "%s:%s" .username .password | b64enc }}"
              }
            }
          }
  data:
    - secretKey: username
      remoteRef: { key: nexus, property: username }
    - secretKey: password
      remoteRef: { key: nexus, property: password }
---
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: order-api-secrets
  namespace: shop
spec:
  refreshInterval: "1m"
  secretStoreRef:
    name: openbao
    kind: ClusterSecretStore
  target:
    name: order-api-secrets
    creationPolicy: Owner
  data:
    - secretKey: ORDER_SIGNING_KEY
      remoteRef: { key: order-api, property: signing_key }
```

```bash
kubectl apply -f deploy/platform/external-secrets.yaml

kubectl -n shop get externalsecret
# NAME                STORE     REFRESH INTERVAL   STATUS         READY
# nexus-pull          openbao   1h                 SecretSynced   True
# order-api-secrets   openbao   1m                 SecretSynced   True

kubectl -n shop get secret nexus-pull order-api-secrets
```

Prove the round trip:

```bash
kubectl -n shop get secret nexus-pull \
  -o jsonpath='{.data.\.dockerconfigjson}' | base64 -d | jq .
```

Now re-run the smoke test that failed in [§5.11](phase-0-foundations.md#511-push-a-first-image-to-prove-the-whole-path):

```bash
kubectl -n shop run smoke --rm -it --restart=Never \
  --image=nexus:8082/smoke/alpine:3.21 \
  --overrides='{"spec":{"imagePullSecrets":[{"name":"nexus-pull"}]}}' \
  -- echo "pulled from nexus using a credential that lives in OpenBao"
```

`creationPolicy: Owner` means ESO owns the Secret and garbage-collects it if the `ExternalSecret` is deleted. That's what you want — otherwise deleting the declaration leaves an orphaned credential in the cluster.

> **`refreshInterval` is a rotation budget, not a preference.** ESO re-reads OpenBao on this interval; if the value changed, it rewrites the Secret. But **an already-running pod does not see the change** — env vars are set at container start and mounted secret volumes update lazily. So the real rotation window is `refreshInterval` + however long until the pod restarts. If you need fast rotation, either mount the secret as a volume and re-read it in-process, or add [Reloader](https://github.com/stakater/Reloader) to restart Deployments when their secrets change. Setting `refreshInterval: 1m` and assuming rotation takes a minute is a mistake people make in production.

Commit:

```bash
git add deploy/ && git commit -m "feat(platform): floci, openbao and external secrets"
```

---

## 8. Kafka with Strimzi

### 8.1 Operator, not StatefulSet

You could write a StatefulSet for Kafka. You'd then own broker ID assignment, rolling restarts that respect in-sync replica counts, certificate rotation, partition rebalancing on scale-up, and KRaft controller quorum management. That is a full-time job.

Strimzi is a Kubernetes **operator**: it turns `Kafka`, `KafkaNodePool` and `KafkaTopic` custom resources into a managed cluster, and encodes the operational knowledge above as controller logic. This is what operators are *for* — stateful software with non-trivial day-2 operations.

> **Modern Kafka is KRaft.** ZooKeeper is gone: Kafka nodes take `controller` and/or `broker` roles and manage metadata via a Raft quorum among the controllers. Strimzi 0.46 and later are KRaft-only (0.45 was the last release supporting ZooKeeper). If you find a tutorial with a `zookeeper:` block in the `Kafka` resource, it is out of date.

### 8.2 Install the operator

```bash
helm repo add strimzi https://strimzi.io/charts/
helm repo update

helm upgrade --install strimzi strimzi/strimzi-kafka-operator \
  --version 0.50.1 \
  --namespace kafka --create-namespace \
  --set watchAnyNamespace=false \
  --wait

kubectl -n kafka get pods
kubectl get crd | grep strimzi
```

`watchAnyNamespace=false` scopes the operator to the `kafka` namespace only. Cluster-wide watching is convenient and is also how one team's malformed CR takes down another team's cluster.

### 8.3 Declare the cluster

Two node pools: a controller quorum and a broker pool. Separating them is the recommended production topology — controllers hold metadata and want stable, small, low-latency nodes; brokers hold data and scale independently.

**`deploy/platform/kafka.yaml`**

```yaml
apiVersion: kafka.strimzi.io/v1beta2
kind: KafkaNodePool
metadata:
  name: controller
  namespace: kafka
  labels:
    strimzi.io/cluster: orders
spec:
  replicas: 3          # Raft quorum: 3 tolerates one failure. Always odd.
  roles:
    - controller
  storage:
    type: jbod
    volumes:
      - id: 0
        type: persistent-claim
        size: 2Gi
        deleteClaim: true
---
apiVersion: kafka.strimzi.io/v1beta2
kind: KafkaNodePool
metadata:
  name: broker
  namespace: kafka
  labels:
    strimzi.io/cluster: orders
spec:
  replicas: 3
  roles:
    - broker
  storage:
    type: jbod
    volumes:
      - id: 0
        type: persistent-claim
        size: 5Gi
        deleteClaim: true
---
apiVersion: kafka.strimzi.io/v1beta2
kind: Kafka
metadata:
  name: orders
  namespace: kafka
  annotations:
    strimzi.io/node-pools: enabled
    strimzi.io/kraft: enabled
spec:
  kafka:
    version: 4.1.0
    metadataVersion: 4.1-IV0
    listeners:
      - name: plain
        port: 9092
        type: internal
        tls: false
    config:
      # With 3 brokers: 3 copies, and a write must reach 2 before it is
      # acknowledged. That survives one broker loss with zero data loss.
      default.replication.factor: 3
      min.insync.replicas: 2
      offsets.topic.replication.factor: 3
      transaction.state.log.replication.factor: 3
      transaction.state.log.min.isr: 2
      auto.create.topics.enable: false
    resources:
      requests: { cpu: 200m, memory: 1Gi }
      limits:   { memory: 2Gi }
  entityOperator:
    topicOperator: {}
    userOperator: {}
---
apiVersion: kafka.strimzi.io/v1beta2
kind: KafkaTopic
metadata:
  name: orders
  namespace: kafka
  labels:
    strimzi.io/cluster: orders
spec:
  partitions: 3
  replicas: 3
  config:
    retention.ms: 604800000     # 7 days
    cleanup.policy: delete
    min.insync.replicas: 2
```

```bash
kubectl apply -f deploy/platform/kafka.yaml

# This takes 3-5 minutes: PVCs bind, controllers form a quorum, then brokers join.
kubectl -n kafka wait kafka/orders --for=condition=Ready --timeout=600s
kubectl -n kafka get pods
kubectl -n kafka get kafkatopic
```

The bootstrap address other namespaces use is:

```
orders-kafka-bootstrap.kafka.svc.cluster.local:9092
```

Four decisions worth naming:

- **`auto.create.topics.enable: false`.** With auto-create on, a typo in a topic name silently produces to a brand-new topic with default settings, and you discover it when a consumer reports zero messages. Off means the typo fails loudly. Declare topics as `KafkaTopic` resources in git — they're config, and config belongs in version control.
- **`min.insync.replicas: 2` with `replicas: 3`.** Producers using `acks=all` (which order-api does) block until 2 replicas have the write. Lose one broker: still writable. Lose two: writes fail rather than silently under-replicating. **Failing writes is the correct behaviour** — the alternative is accepting data you cannot guarantee.
- **3 partitions.** Partition count caps consumer parallelism: 3 partitions means at most 3 useful `order-worker` replicas in one consumer group. You can increase partitions later but never decrease, and increasing changes key→partition mapping, which breaks per-key ordering for in-flight keys. Size it for growth on day one.
- **`deleteClaim: true`.** PVCs are deleted with the cluster. Right for a laptop, catastrophic in production — set `false` there so an accidental `kubectl delete kafka` doesn't take your data with it.

### 8.4 Verify with a real produce/consume

```bash
# Producer (leave this running, type messages, Ctrl-C to exit)
kubectl -n kafka run kafka-producer -ti --rm --restart=Never \
  --image=quay.io/strimzi/kafka:0.50.1-kafka-4.1.0 -- \
  bin/kafka-console-producer.sh \
    --bootstrap-server orders-kafka-bootstrap:9092 \
    --topic orders
```

In a second terminal:

```bash
kubectl -n kafka run kafka-consumer -ti --rm --restart=Never \
  --image=quay.io/strimzi/kafka:0.50.1-kafka-4.1.0 -- \
  bin/kafka-console-consumer.sh \
    --bootstrap-server orders-kafka-bootstrap:9092 \
    --topic orders --from-beginning
```

Type in the producer, see it in the consumer. Ctrl-C both.

```bash
git add deploy/platform/kafka.yaml && git commit -m "feat(platform): kafka via strimzi in kraft mode"
```

---

## 10. Packaging the app with Helm

### 10.1 One chart, two workloads

**`deploy/charts/order-platform/Chart.yaml`**

```yaml
apiVersion: v2
name: order-platform
description: order-api (FastAPI) and order-worker (Go)
type: application
version: 0.1.0
appVersion: "0.1.0"
```

**`deploy/charts/order-platform/values.yaml`**

```yaml
# Defaults. Environment overlays in deploy/env/<env>/values.yaml override these,
# and CI rewrites the image tags there — never here.
global:
  registry: nexus:8082
  imagePullSecret: nexus-pull

kafka:
  brokers: "orders-kafka-bootstrap.kafka.svc.cluster.local:9092"
  topic: "orders"

aws:
  endpointUrl: "http://floci.floci.svc.cluster.local:4566"
  region: "us-east-1"
  s3Bucket: "orders-raw"
  ddbTable: "orders"

orderApi:
  enabled: true
  image:
    repository: shop/order-api
    tag: "dev"
  replicas: 2
  port: 8000
  secretName: order-api-secrets     # produced by the ExternalSecret in §7.6
  resources:
    requests: { cpu: 50m, memory: 128Mi }
    limits:   { memory: 256Mi }
  ingress:
    enabled: true
    className: nginx
    host: shop.localtest.me

orderWorker:
  enabled: true
  image:
    repository: shop/order-worker
    tag: "dev"
  replicas: 2          # <= partition count (3), see §8.3
  metricsPort: 9090
  consumerGroup: order-worker
  resources:
    requests: { cpu: 50m, memory: 64Mi }
    limits:   { memory: 128Mi }

podMonitor:
  # false until §13.2 installs kube-prometheus-stack and with it the
  # monitoring.coreos.com CRDs. Argo CD does not skip a resource whose CRD is
  # missing — it fails the whole sync, so leaving this true strands every
  # workload in `shop` as Missing. Flip to true in §13.3 and commit.
  enabled: false
  interval: 15s

scaffolded:
  tag: "dev"     # CI overwrites this in the env overlay, same as the other two
```

> [!warning] **Leave `podMonitor.enabled: false` until [§13.3](phase-2-observability.md#133-confirm-your-app-is-being-scraped).**
> Argo CD syncs an Application as a unit, so a resource whose CRD is missing fails the *entire* sync —
> with `podMonitor.enabled: true`, `monitoring.coreos.com/v1` does not exist until
> [§13.2](phase-2-observability.md#132-install) and every workload in `shop` stays `Missing`. The flag
> belongs in the **chart's** `values.yaml`, not in `deploy/env/local/values.yaml`, which Buildkite
> rewrites wholesale on every deploy ([§12.5](phase-3-delivery.md#125-the-pipeline)).

**`deploy/charts/order-platform/templates/_helpers.tpl`**

```yaml
{{- define "op.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .root.Chart.Name .root.Chart.Version | replace "+" "_" }}
app.kubernetes.io/name: {{ .name }}
app.kubernetes.io/instance: {{ .root.Release.Name }}
app.kubernetes.io/part-of: order-platform
app.kubernetes.io/managed-by: {{ .root.Release.Service }}
app.kubernetes.io/version: {{ .root.Chart.AppVersion | quote }}
{{- end -}}

{{- define "op.image" -}}
{{- printf "%s/%s:%s" .root.Values.global.registry .img.repository .img.tag -}}
{{- end -}}

{{/*
Common env shared by both services. Keeping this in one place is the whole
reason we wrote a chart instead of two YAML files.
*/}}
{{- define "op.commonEnv" -}}
- name: KAFKA_BROKERS
  value: {{ .Values.kafka.brokers | quote }}
- name: KAFKA_TOPIC
  value: {{ .Values.kafka.topic | quote }}
- name: AWS_ENDPOINT_URL
  value: {{ .Values.aws.endpointUrl | quote }}
- name: AWS_DEFAULT_REGION
  value: {{ .Values.aws.region | quote }}
- name: AWS_ACCESS_KEY_ID
  value: "test"
- name: AWS_SECRET_ACCESS_KEY
  value: "test"
{{- end -}}
```

> **The label set is Helm's recommended one, and the selector is deliberately not.** `helm.sh/chart`
> tells you which chart version produced a live object, which is the first thing you want in an
> incident; `app.kubernetes.io/instance` is what stops two releases of this chart in one namespace
> colliding on every resource. Both belong on the object. Neither belongs in
> `selector.matchLabels`, which stays `app.kubernetes.io/name` alone — a Deployment's selector is
> **immutable**, so a label added there can never be changed without deleting and recreating the
> workload, and `helm.sh/chart` changes on every chart bump. Put in a selector only what you will
> never need to edit.

> The static `AWS_ACCESS_KEY_ID: test` is a Floci-ism: the emulator ignores credentials but the AWS SDKs refuse to sign a request without them. In a real cluster these two lines disappear entirely and the pod gets credentials from IRSA / Workload Identity via the ServiceAccount. **That is the one place where "same binary everywhere" leaks** — worth knowing so it doesn't surprise you at promotion time.

**`deploy/charts/order-platform/templates/order-api.yaml`**

```yaml
{{- if .Values.orderApi.enabled }}
apiVersion: v1
kind: ServiceAccount
metadata:
  name: order-api
  labels: {{- include "op.labels" (dict "name" "order-api" "root" $) | nindent 4 }}
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-api
  labels: {{- include "op.labels" (dict "name" "order-api" "root" $) | nindent 4 }}
spec:
  replicas: {{ .Values.orderApi.replicas }}
  selector:
    matchLabels:
      app.kubernetes.io/name: order-api
  strategy:
    type: RollingUpdate
    rollingUpdate: { maxSurge: 1, maxUnavailable: 0 }
  template:
    metadata:
      labels: {{- include "op.labels" (dict "name" "order-api" "root" $) | nindent 8 }}
      annotations:
        # Roll the pods whenever the rendered config changes. Without this,
        # `helm upgrade` with only a value change leaves old pods running.
        checksum/config: {{ toJson .Values | sha256sum }}
        # Istio's agent reads these three, scrapes the app over loopback inside
        # the pod, and re-publishes the result merged with Envoy's own metrics
        # on port 15020. That merged endpoint is what Prometheus scrapes — see
        # §9.6 for why it cannot scrape port 8000 directly any more.
        prometheus.io/scrape: "true"
        prometheus.io/path: "/metrics"
        prometheus.io/port: {{ .Values.orderApi.port | quote }}
    spec:
      # Kubernetes injects a Docker-link env var per Service in this namespace:
      # ORDER_API_PORT, ORDER_WORKER_PORT — each set to "tcp://<clusterIP>:<port>".
      # Any app reading a variable of that name as its own config gets a URL where
      # it expected an integer, and env vars outrank every other config source.
      # Service links are a Docker-links relic nothing here uses.
      enableServiceLinks: false
      serviceAccountName: order-api
      imagePullSecrets:
        - name: {{ .Values.global.imagePullSecret }}
      securityContext:
        runAsNonRoot: true
        seccompProfile: { type: RuntimeDefault }
      containers:
        - name: order-api
          image: {{ include "op.image" (dict "root" $ "img" .Values.orderApi.image) }}
          imagePullPolicy: IfNotPresent
          ports:
            - { name: http, containerPort: {{ .Values.orderApi.port }} }
          env:
            {{- include "op.commonEnv" . | nindent 12 }}
            - name: S3_BUCKET
              value: {{ .Values.aws.s3Bucket | quote }}
            - name: SERVICE_VERSION
              value: {{ .Values.orderApi.image.tag | quote }}
            - name: ORDER_SIGNING_KEY
              valueFrom:
                secretKeyRef:
                  name: {{ .Values.orderApi.secretName }}
                  key: ORDER_SIGNING_KEY
          startupProbe:
            # Gives a slow start up to 60s without loosening the liveness probe,
            # which stays tight so a genuinely wedged pod is killed fast.
            httpGet: { path: /healthz, port: http }
            failureThreshold: 20
            periodSeconds: 3
          livenessProbe:
            httpGet: { path: /healthz, port: http }
            periodSeconds: 10
            failureThreshold: 3
          readinessProbe:
            httpGet: { path: /readyz, port: http }
            periodSeconds: 5
            failureThreshold: 2
          resources: {{- toYaml .Values.orderApi.resources | nindent 12 }}
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities: { drop: ["ALL"] }
---
apiVersion: v1
kind: Service
metadata:
  name: order-api
  labels: {{- include "op.labels" (dict "name" "order-api" "root" $) | nindent 4 }}
spec:
  selector:
    app.kubernetes.io/name: order-api
  ports:
    - { name: http, port: 80, targetPort: http }
{{- if .Values.orderApi.ingress.enabled }}
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: order-api
spec:
  ingressClassName: {{ .Values.orderApi.ingress.className }}
  rules:
    - host: {{ .Values.orderApi.ingress.host }}
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: order-api
                port: { name: http }
{{- end }}
{{- end }}
```

> **`maxUnavailable: 0` + `maxSurge: 1`.** Kubernetes brings up a new pod *before* removing an old one, so capacity never dips during a deploy. It costs one pod's worth of headroom and requires that two versions can run simultaneously — which forces the discipline of backwards-compatible changes. The alternative (`maxUnavailable: 1`) deploys with no extra capacity but drops throughput mid-roll. For anything serving traffic, take the surge.

> **`readOnlyRootFilesystem: true`.** If the app is compromised, the attacker can't drop a binary on disk. It also catches applications that quietly write to `/tmp` — if a pod crashes after you set this, that's a finding, not a reason to turn it off. Add an `emptyDir` volume for legitimate scratch space instead.

**`deploy/charts/order-platform/templates/order-worker.yaml`**

```yaml
{{- if .Values.orderWorker.enabled }}
apiVersion: v1
kind: ServiceAccount
metadata:
  name: order-worker
  labels: {{- include "op.labels" (dict "name" "order-worker" "root" $) | nindent 4 }}
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-worker
  labels: {{- include "op.labels" (dict "name" "order-worker" "root" $) | nindent 4 }}
spec:
  replicas: {{ .Values.orderWorker.replicas }}
  selector:
    matchLabels:
      app.kubernetes.io/name: order-worker
  strategy:
    # A consumer group rebalances on every membership change. Rolling one pod at
    # a time keeps rebalances short; surging would add a member and then remove
    # one, causing two rebalances per pod instead of one.
    type: RollingUpdate
    rollingUpdate: { maxSurge: 0, maxUnavailable: 1 }
  template:
    metadata:
      labels: {{- include "op.labels" (dict "name" "order-worker" "root" $) | nindent 8 }}
      annotations:
        checksum/config: {{ toJson .Values | sha256sum }}
        prometheus.io/scrape: "true"
        prometheus.io/path: "/metrics"
        prometheus.io/port: {{ .Values.orderWorker.metricsPort | quote }}
    spec:
      # Same reason as order-api: no Docker-link env vars in this pod.
      enableServiceLinks: false
      serviceAccountName: order-worker
      imagePullSecrets:
        - name: {{ .Values.global.imagePullSecret }}
      # Give the worker time to finish the in-flight batch and commit offsets
      # after SIGTERM before Kubernetes SIGKILLs it.
      terminationGracePeriodSeconds: 45
      securityContext:
        runAsNonRoot: true
        seccompProfile: { type: RuntimeDefault }
      containers:
        - name: order-worker
          image: {{ include "op.image" (dict "root" $ "img" .Values.orderWorker.image) }}
          imagePullPolicy: IfNotPresent
          ports:
            # http-metrics, not metrics. Istio reads the protocol off the port
            # name, and a name it does not recognise is treated as plain TCP.
            - { name: http-metrics, containerPort: {{ .Values.orderWorker.metricsPort }} }
          env:
            {{- include "op.commonEnv" . | nindent 12 }}
            - name: DDB_TABLE
              value: {{ .Values.aws.ddbTable | quote }}
            - name: KAFKA_GROUP
              value: {{ .Values.orderWorker.consumerGroup | quote }}
            - name: SERVICE_VERSION
              value: {{ .Values.orderWorker.image.tag | quote }}
          startupProbe:
            httpGet: { path: /healthz, port: http-metrics }
            failureThreshold: 30
            periodSeconds: 2
          livenessProbe:
            httpGet: { path: /healthz, port: http-metrics }
            periodSeconds: 10
            failureThreshold: 3
          readinessProbe:
            httpGet: { path: /readyz, port: http-metrics }
            periodSeconds: 5
          resources: {{- toYaml .Values.orderWorker.resources | nindent 12 }}
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities: { drop: ["ALL"] }
---
apiVersion: v1
kind: Service
metadata:
  name: order-worker
  labels: {{- include "op.labels" (dict "name" "order-worker" "root" $) | nindent 4 }}
spec:
  selector:
    app.kubernetes.io/name: order-worker
  ports:
    - { name: http-metrics, port: 9090, targetPort: http-metrics }
{{- end }}
```

> **Port names are an Istio interface, so `http-metrics` and not `metrics`.** Istio picks a port's
> protocol from the Service port name, whose expected syntax is `<protocol>[-<suffix>]` — `http`,
> `http-metrics`, `grpc-pricing`. A name outside that convention falls back to automatic protocol
> detection, which is best-effort and which `istioctl analyze` flags as
> [IST0118](https://istio.io/latest/docs/reference/config/analysis/ist0118). Lose HTTP and you lose
> the L7 features that are the reason you installed a mesh: per-route routing, retries, and
> `istio_requests_total` with a response code in it. `appProtocol` does the same job explicitly and
> wins over the name where both are set. The container port carries the same name so the probes and
> the Service refer to one thing; nothing in Istio reads the container port name.
>
> This bites at [Phase 4](phase-4-service-mesh.md), not here — which is exactly why it goes in now.
> Renaming a port later means editing the Service, the probes and every monitor that selects by name.

**`deploy/charts/order-platform/templates/podmonitor.yaml`**

```yaml
{{- if .Values.podMonitor.enabled }}
apiVersion: monitoring.coreos.com/v1
kind: PodMonitor
metadata:
  name: order-platform
  labels:
    # kube-prometheus-stack's Prometheus selects monitors by this label in the
    # default configuration we install in §13.
    release: monitoring
spec:
  namespaceSelector:
    matchNames: ["shop"]
  selector:
    matchLabels:
      app.kubernetes.io/part-of: order-platform
  podMetricsEndpoints:
    # istio-proxy's MERGED endpoint on 15020: our application metrics (scraped
    # over loopback inside the pod, per the prometheus.io/* annotations above)
    # plus Envoy's and Istio's. One scrape, all of it, and it survives STRICT.
    #
    # It must be 15020 and it must be addressed by number. Istio: "forwards
    # requests to the sidecar telemetry port 15020 for merged metrics or 15090
    # for Envoy-only metrics". 15090 is the one carrying the port NAME
    # `http-envoy-prom`; 15020 is unnamed in the pod spec, so `port:` cannot
    # reach it and `portNumber:` is required. Selecting http-envoy-prom gets
    # you istio_requests_total (Kiali works) but never the application's own
    # metrics, which is a silent half-failure.
    - portNumber: 15020
      path: /stats/prometheus
      interval: {{ .Values.podMonitor.interval }}
{{- end }}
```

> **Why a PodMonitor and not a ServiceMonitor.** A `ServiceMonitor` selects *Services* and scrapes their endpoints by port name — which is exactly what we did before Istio, with one entry for order-api's `http` port and one for order-worker's `http-metrics`. Under STRICT mTLS ([§9.6](phase-4-service-mesh.md#96-the-metrics-problem-you-just-created)) both of those scrapes get a connection reset, because Prometheus has no sidecar and no certificate. The merged endpoint lives on the *pod*, on the sidecar's own port, and is not fronted by a Service — so a `PodMonitor` is the only monitor kind that can reach it. `http-envoy-prom` is the port name Istio gives 15090 on every injected pod; `/stats/prometheus` there serves Envoy's metrics with the application's merged in.

> **The trap in this swap:** if a pod has no sidecar, it has no `http-envoy-prom` port, so the PodMonitor silently matches nothing and that workload vanishes from Prometheus with no error. A workload that leaves the mesh loses its metrics. Worth an alert of its own — `absent(up{job="order-platform"})` — which is precisely the kind of "the monitoring stopped" condition [§13.5](phase-2-observability.md#135-an-alert-that-means-something) argues you should page on.

### 10.2 The environment overlay

**`deploy/env/local/values.yaml`**

```yaml
# This file is the deployment contract. Buildkite rewrites the two image tags
# below and commits; Argo CD notices and syncs. Nothing else writes here.
orderApi:
  image:
    tag: "dev"
orderWorker:
  image:
    tag: "dev"
```

### 10.3 Render it before you trust it

`helm template` renders locally without touching the cluster. Do this every time you edit a chart.

```bash
helm template order-platform deploy/charts/order-platform \
  --namespace shop \
  --values deploy/env/local/values.yaml | head -60

# Catch schema errors against the live API without applying:
helm template order-platform deploy/charts/order-platform \
  --namespace shop --values deploy/env/local/values.yaml \
  | kubectl apply --dry-run=server -f -
```

Everything should validate. With `podMonitor.enabled: false` the chart renders nothing that needs a
CRD the cluster doesn't have yet — which is exactly why the flag starts off.

### 10.4 Build the images, by hand, once

Nothing has built your services yet. CI does that from [Phase 3](phase-3-delivery.md) onward; right
now you are the CI.

```bash
SHA="$(git rev-parse --short=12 HEAD)"

for svc in order-api order-worker; do
  docker build -f "services/$svc/Dockerfile" -t "nexus:8082/shop/$svc:$SHA" "services/$svc"
  docker push "nexus:8082/shop/$svc:$SHA"
done

echo "$SHA"
```

> **Use the commit SHA, not `latest`, even by hand.** It costs nothing here and it is the habit the
> whole delivery story depends on later ([§10.3](#103-render-it-before-you-trust-it)). A tag that can
> change meaning turns "what is running?" into a question nobody can answer.

Point the overlay at what you just pushed:

```bash
sed -i.bak "s|tag: \".*\"|tag: \"$SHA\"|g" deploy/env/local/values.yaml && rm deploy/env/local/values.yaml.bak
grep tag: deploy/env/local/values.yaml
```

### 10.5 Install it

```bash
helm upgrade --install order-platform deploy/charts/order-platform \
  --namespace shop --create-namespace \
  --values deploy/env/local/values.yaml \
  --wait --timeout 5m

kubectl -n shop get pods
```

All four pods should reach `Running` and `1/1`. Not `2/2` — there is no sidecar yet; that is
[Phase 4](phase-4-service-mesh.md).

**Now the whole point of the phase:**

```bash
for i in $(seq 1 20); do
  curl -sS -o /dev/null -w '%{http_code} ' -X POST http://shop.localtest.me/orders \
    -H 'content-type: application/json' \
    -d '{"customer":"ada","sku":"WIDGET-1","quantity":1,"amount_cents":1999}'
done; echo
```

Twenty `202`s. Then confirm the data actually landed at both ends — the API's write to S3, and the
worker's write to DynamoDB after it consumed the Kafka event:

```bash
kubectl -n floci run awscli --rm -i --restart=Never --image=amazon/aws-cli:2.32.9 \
  --env AWS_ENDPOINT_URL=http://floci.floci.svc.cluster.local:4566 \
  --env AWS_ACCESS_KEY_ID=test --env AWS_SECRET_ACCESS_KEY=test \
  --env AWS_DEFAULT_REGION=us-east-1 -- \
  s3 ls s3://orders-raw/orders/ --recursive | tail -3

kubectl -n floci run awscli --rm -i --restart=Never --image=amazon/aws-cli:2.32.9 \
  --env AWS_ENDPOINT_URL=http://floci.floci.svc.cluster.local:4566 \
  --env AWS_ACCESS_KEY_ID=test --env AWS_SECRET_ACCESS_KEY=test \
  --env AWS_DEFAULT_REGION=us-east-1 -- \
  dynamodb scan --table-name orders --select COUNT
```

`Count` should equal the number of orders you posted. If S3 has objects and DynamoDB has none, the
API is fine and the worker is not — start with `kubectl -n shop logs deploy/order-worker`.

> **What you just did, and why Phase 3 exists.** You built an image, remembered its tag, edited a
> file, and ran `helm upgrade` from a laptop that happens to have cluster credentials. It works.
> Now notice: nothing recorded any of it, the only record of *what is deployed* is the cluster
> itself, and the deploy required you to be awake. Hold onto that feeling — it is the entire argument
> for [Phase 3](phase-3-delivery.md), and it is much more convincing now than it would have been as
> an assertion three phases ago.

### 10.6 Tradeoff: Helm vs Kustomize

| | Helm | Kustomize |
|---|---|---|
| Mechanism | Go templates → YAML | Strategic merge patches on real YAML |
| Best at | distributing software to strangers; conditional/parameterised output | overlaying environments onto manifests you own |
| Failure mode | template logic becomes a program nobody can read; `{{- if }}` nesting three deep | patch files multiply; hard to see the final object without rendering |
| Versioned artifact | yes, charts are packaged and pushed to a registry | no native packaging |
| Rollback | `helm rollback` (release history in-cluster) | whatever git says |

We use Helm because we need one thing Kustomize genuinely can't do cleanly: **a single parameter that CI can mechanically rewrite**, with the rest of the manifest derived from it. Kustomize's `images:` transformer does exactly this too, and if your only variance across environments is image tags and replica counts, Kustomize is the simpler, more auditable choice — you can read the output without rendering anything.

The rule of thumb: **Helm for software you ship to others, Kustomize for software you run yourself.** We're technically on the wrong side of that rule and doing it anyway, because you will spend your career reading other people's charts and it's worth building the muscle. Note that Argo CD supports both natively — this is not a lock-in decision.

```bash
git add deploy/ && git commit -m "feat(deploy): helm chart for order-platform"
```

---

## Where you are

`curl -X POST http://shop.localtest.me/orders` returns `202`. The payload is signed with a key that
only ever existed in OpenBao, written to S3, published to Kafka, consumed by `order-worker` and
written to DynamoDB. That is a real distributed system, on a laptop, with no cloud account.

It is also entirely undefended and entirely unobserved:

- You cannot tell whether it is healthy without `kubectl logs`.
- Deploying means you, typing, remembering an image tag.
- Any pod in the cluster can call `floci` directly.

**Next: [Phase 2 — Seeing what it does](phase-2-observability.md)**, because the first of those is
the one that makes the other two safe to fix.

[← All phases](README.md) · [← Phase 0 — Foundations](phase-0-foundations.md) · [Phase 2 — Seeing what it does →](phase-2-observability.md)

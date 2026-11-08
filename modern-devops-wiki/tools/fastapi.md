---
type: tool
tags: [python, framework, service]
role: order-api, and the scaffolded-service skeleton
version: 0.139.2
docs: https://fastapi.tiangolo.com/
date_added: 2026-08-17
date_updated: 2026-08-17
status: in-use
---

# FastAPI

> [!info] One-liner
> order-api: accepts an order, prices it over [[grpc]], signs it, writes it to S3, publishes it to [[apache-kafka]]. Every scaffolded service is the same shape with the parts a new service does not have removed.

## The service contract both languages honour (§3)

Config from environment variables only. `GET /healthz` (liveness), `GET /readyz` (readiness),
`GET /metrics` (Prometheus text), structured JSON logs to stdout, non-root user in the image.
*Consistency across runtimes is the point of a platform.*

## Async discipline, which is where FastAPI is easy to get wrong

**`/metrics` is mounted, not routed.** `prometheus_client` ships an ASGI app and its docs prescribe
mounting it — it negotiates content type and compression, and a mount is not a route, so `/metrics`
stays out of the OpenAPI document [[backstage]] renders.

**boto3 is synchronous, so the S3 write goes to the threadpool.** Called directly from an `async def`
endpoint it blocks the event loop for the whole round trip — every other in-flight request, **and both
probes**, stall with it. `run_in_threadpool` is FastAPI's documented answer.

> The rule that decides whether a handler is `async def` at all: **an `async def` endpoint may only
> `await`.** A handler with blocking work and no threadpool should be a plain `def`, which FastAPI then
> runs in the threadpool itself.

A test pins this by recording the thread `_FakeS3` ran on and asserting it differs from
`threading.current_thread().name`. It exists because the defect is otherwise invisible.

**`/readyz` is `async def`** because the pricing health check is a real awaited RPC. See
[[health-checks]].

## Exception ordering that is not obvious

```python
except HTTPException:
    ORDERS_RECEIVED.labels(result="error").inc()
    raise
except Exception:
    ORDERS_RECEIVED.labels(result="error").inc()
    log.exception(...)
    raise HTTPException(status_code=502, detail="downstream failure")
```

Without the first clause the bare `except Exception` swallows the `HTTPException` from `_price_order`
and re-raises a flat 502 — throwing away the status the gRPC code was translated to, and logging a
stack trace for a downstream failure that was already handled and counted.

## Side-effect ordering

**Price → S3 → Kafka.** The price is part of the record, so an order that cannot be priced must not
reach S3 or Kafka at all. And S3 before Kafka: a failed publish leaves an orphan object (cheap,
recoverable), while publish-first with a failed S3 write leaves the worker consuming an event pointing
at an object that does not exist. **Order your side effects so the recoverable failure is the likely
one.**

## The OpenAPI spec is derived, never authored

FastAPI builds the document from route signatures at runtime, so `services/order-api/openapi.json` can
only be a snapshot. `pants run services/order-api:dump-openapi` regenerates it and
`services/order-api/tests/test_openapi_spec.py` fails the build when the two drift. **A hand-maintained API spec is a lie
with a timestamp on it** — see [[backstage]] (§19.6).

## The tests are deliberately thin

Their job is to prove the *pipeline* runs them and fails the build when they fail, not to demonstrate
test design (§3.1). The exceptions are the ones pinning decisions that would otherwise be quietly
reversed: the gRPC-status mapping table, the no-fallback behaviour, the threadpool assertion, and
readiness-via-health-protocol. A fallback would have to change every expected status in the
parametrised test, **which is the point.**

## Related

[[pydantic]] · [[grpc]] · [[apache-kafka]] · [[floci]] · [[pex]] · [[uv]] · [[health-checks]] · [[backstage]] · [[prometheus]]

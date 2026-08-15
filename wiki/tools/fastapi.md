---
type: tool
tags: [python, web-framework, application]
role: order-api — the HTTP intake service
version: FastAPI 0.139.2, Python 3.13
docs: https://fastapi.tiangolo.com/
date_added: 2026-08-15
date_updated: 2026-08-15
status: in-use
---

# FastAPI

> [!info] One-liner
> An async Python web framework where Pydantic type hints *are* the validation, the serialisation and the OpenAPI schema.

## What it does here

`services/order-api` (§3.1): accepts `POST /orders`, writes the raw payload to S3 via [[floci]],
produces an event to [[apache-kafka]], and exposes `/healthz`, `/readyz` and `/metrics`.

It follows the platform's service contract, which matters more than the framework choice: **health
and readiness as separate endpoints, Prometheus metrics, structured JSON logs, config from
environment**. order-worker in Go implements the identical contract — consistency across runtimes is
the point of a platform.

## Key concepts

- **Pydantic models do double duty**: request validation and the generated OpenAPI schema. Invalid
  input is rejected before your handler runs.
- **`/healthz` vs `/readyz` are different questions.** Liveness = "should Kubernetes kill me";
  readiness = "should traffic come to me". Conflating them causes restart loops during dependency
  blips. The chart also uses a `startupProbe` so a slow start doesn't require loosening liveness.
- **Settings read at import time** means the environment must be set before import — which is why the
  test suite sets env vars before importing the app.
- ASGI/`uvicorn` is the server; FastAPI is the framework.
- **Pydantic is a compiled dependency.** `pydantic-core` is Rust, shipped as wheels per CPython
  version — so the Python interpreter you use is not a free choice. See the pinning warning in
  [[uv]]; an unpinned interpreter turns `uv run pytest` into a Rust build failure.

## Official docs

- Docs: https://fastapi.tiangolo.com/
- Deployment concepts: https://fastapi.tiangolo.com/deployment/concepts/
- Pydantic: https://docs.pydantic.dev/latest/

> [!tip] Related
> [[uv]], [[apache-kafka]], [[floci]], [[prometheus]], [[order-platform]]

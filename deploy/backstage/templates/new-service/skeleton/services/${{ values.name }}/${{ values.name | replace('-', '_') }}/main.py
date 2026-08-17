import logging
import sys
import time

import uvicorn  # pants: no-infer-dep  (via fastapi[standard])
from fastapi import FastAPI
from prometheus_client import Counter, Histogram, make_asgi_app

from .settings import settings

SERVICE = "${{ values.name }}"

# Prometheus metric names allow [a-zA-Z_:][a-zA-Z0-9_:]* — service names are
# hyphenated, so derive the prefix here rather than templating it. Doing it in
# Python instead of in the scaffolder keeps the skeleton readable and means a
# rename can never emit an invalid metric name.
METRIC_PREFIX = SERVICE.replace("-", "_")

logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format='{"ts":"%(asctime)s","level":"%(levelname)s","msg":"%(message)s"}',
)
log = logging.getLogger(SERVICE)

REQUESTS = Counter(
    f"{METRIC_PREFIX}_requests_total", "Requests handled", ["route", "result"]
)
LATENCY = Histogram(
    f"{METRIC_PREFIX}_request_duration_seconds", "Time to handle one request"
)

app = FastAPI(title=SERVICE, version=settings.service_version)

# prometheus_client ships an ASGI app for this; mounting it is what its docs
# prescribe. It negotiates content type and compression, and a mount is not a
# route, so /metrics stays out of the OpenAPI document Backstage renders.
# https://prometheus.github.io/client_python/exporting/http/fastapi-gunicorn/
app.mount("/metrics", make_asgi_app())


@app.get("/healthz")
def healthz() -> dict:
    """Liveness: the process is running. Deliberately checks nothing else."""
    return {"status": "ok", "version": settings.service_version}


@app.get("/readyz")
def readyz() -> dict:
    """Readiness: this service has no external dependencies yet.

    When you add one — a database, a queue, another service — check it *here*
    and not in /healthz. Liveness that depends on a downstream turns that
    downstream's outage into a restart loop across every one of your pods.
    """
    return {"status": "ready"}


@app.get("/")
def root() -> dict:
    """Replace me. Present so the service does something observable on day one."""
    started = time.perf_counter()
    try:
        payload = {"service": SERVICE, "description": "${{ values.description }}"}
    except Exception:
        REQUESTS.labels(route="/", result="error").inc()
        raise
    finally:
        LATENCY.observe(time.perf_counter() - started)

    REQUESTS.labels(route="/", result="ok").inc()
    return payload


def main() -> None:
    """Entry point for the packaged pex_binary: run the ASGI app under uvicorn."""
    uvicorn.run(app, host="0.0.0.0", port=settings.port)


if __name__ == "__main__":
    main()

import logging
import sys
import time

from fastapi import FastAPI, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

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


@app.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


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

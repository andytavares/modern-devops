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

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
from fastapi import FastAPI, HTTPException, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
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


class PricingClient:
    """Thin async wrapper around the generated Pricing stub.

    Uses grpc.aio so a slow or unavailable pricing service can't block the
    event loop. Deliberately has no fallback path: a failed price is a failed
    order, not a locally guessed one.
    """

    def __init__(self, address: str, timeout_seconds: float) -> None:
        self._channel = grpc.aio.insecure_channel(address)
        self._stub = pricing_pb2_grpc.PricingStub(self._channel)
        self._timeout_seconds = timeout_seconds

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

    def is_ready(self) -> bool:
        state = self._channel.get_state(try_to_connect=True)
        return state not in (
            grpc.ChannelConnectivity.TRANSIENT_FAILURE,
            grpc.ChannelConnectivity.SHUTDOWN,
        )

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
        settings.pricing_addr, settings.pricing_timeout_seconds
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
    pricing = state["pricing"]
    if pricing is None or not pricing.is_ready():
        raise HTTPException(status_code=503, detail="pricing channel not ready")
    return {"status": "ready"}


@app.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


async def _price_order(order: OrderIn) -> pricing_pb2.PriceOrderResponse:
    """Call shop.v1.Pricing/PriceOrder. Raises HTTPException(502) on any failure —
    never falls back to a locally computed price, so a pricing outage is a visible
    order failure rather than a silently wrong total."""
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
        raise HTTPException(status_code=502, detail="pricing unavailable") from exc
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
        state["s3"].put_object(
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

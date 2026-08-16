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

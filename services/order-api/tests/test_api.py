import asyncio
import os

# Settings are read at import time, so the environment must be set first.
os.environ.setdefault("KAFKA_BROKERS", "localhost:9092")
os.environ.setdefault("S3_BUCKET", "test-bucket")
os.environ.setdefault("ORDER_SIGNING_KEY", "test-key")

import grpc  # noqa: E402
import pytest  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from order_api.main import OrderIn, app, create_order, healthz, state  # noqa: E402
from shop.v1 import pricing_pb2  # noqa: E402


class _FakeS3:
    def put_object(self, **kwargs):
        pass


class _FakeProducer:
    async def send_and_wait(self, *args, **kwargs):
        pass


class _FakePricingClient:
    """Stands in for PricingClient so tests never touch the network."""

    def __init__(self, *, response=None, error: grpc.RpcError | None = None):
        self._response = response
        self._error = error

    async def price_order(self, **kwargs):
        if self._error is not None:
            raise self._error
        return self._response


class _FakeRpcError(grpc.RpcError):
    def __init__(self, code: grpc.StatusCode):
        self._code = code

    def code(self) -> grpc.StatusCode:
        return self._code


def _order() -> OrderIn:
    return OrderIn(customer="ada", sku="W-1", quantity=3, amount_cents=4999)


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


def test_order_response_includes_pricing_result():
    state["s3"] = _FakeS3()
    state["producer"] = _FakeProducer()
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


def test_pricing_timeout_returns_502():
    from fastapi import HTTPException

    state["s3"] = _FakeS3()
    state["producer"] = _FakeProducer()
    state["pricing"] = _FakePricingClient(
        error=_FakeRpcError(grpc.StatusCode.DEADLINE_EXCEEDED)
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(create_order(_order()))

    assert exc_info.value.status_code == 502


def test_pricing_unavailable_returns_502():
    from fastapi import HTTPException

    state["s3"] = _FakeS3()
    state["producer"] = _FakeProducer()
    state["pricing"] = _FakePricingClient(
        error=_FakeRpcError(grpc.StatusCode.UNAVAILABLE)
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(create_order(_order()))

    assert exc_info.value.status_code == 502

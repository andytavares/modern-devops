import json
import logging
import signal
import sys
import threading
import time
from concurrent import futures
from http.server import BaseHTTPRequestHandler, HTTPServer
from types import FrameType

import grpc
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from shop.v1 import pricing_pb2, pricing_pb2_grpc

from .settings import settings  # pants: no-infer-dep (already colocated in this target)

# ---------- logging ----------
logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format='{"ts":"%(asctime)s","level":"%(levelname)s","msg":"%(message)s"}',
)
log = logging.getLogger("pricing")

# ---------- metrics ----------
PRICING_REQUESTS = Counter(
    "pricing_requests_total",
    "Priced orders, by rule and serving version",
    ["rule", "version"],
)
PRICING_DURATION = Histogram(
    "pricing_request_duration_seconds", "Time to price one order"
)

# ---------- readiness ----------
ready_event = threading.Event()


def calculate_price(
    quantity: int, unit_amount_cents: int, version: str
) -> tuple[int, int, str]:
    """Pure pricing logic, version-switched.

    v1: list price, no discount.
    v2: same, but a 3+ quantity line gets 10% off (integer math, rounded down).
    """
    list_total = unit_amount_cents * quantity
    discount_cents = 0
    rule_applied = "list-price"
    if version == "v2" and quantity >= 3:
        discount_cents = (list_total * 10) // 100
        rule_applied = "bulk-10pct"
    return list_total - discount_cents, discount_cents, rule_applied


def validate_request(sku: str, quantity: int, unit_amount_cents: int) -> None:
    """Raises ValueError with a useful message on invalid input."""
    if not sku:
        raise ValueError("sku must not be empty")
    if quantity < 1:
        raise ValueError(f"quantity must be >= 1, got {quantity}")
    if unit_amount_cents < 1:
        raise ValueError(f"unit_amount_cents must be >= 1, got {unit_amount_cents}")


class PricingServicer(pricing_pb2_grpc.PricingServicer):
    def PriceOrder(
        self, request: pricing_pb2.PriceOrderRequest, context: grpc.ServicerContext
    ) -> pricing_pb2.PriceOrderResponse:
        started = time.perf_counter()
        try:
            validate_request(request.sku, request.quantity, request.unit_amount_cents)
        except ValueError as exc:
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details(str(exc))
            return pricing_pb2.PriceOrderResponse()

        total_amount_cents, discount_cents, rule_applied = calculate_price(
            request.quantity, request.unit_amount_cents, settings.version
        )

        PRICING_REQUESTS.labels(rule=rule_applied, version=settings.version).inc()
        PRICING_DURATION.observe(time.perf_counter() - started)
        log.info(
            "priced sku=%s quantity=%d rule=%s served_by=%s",
            request.sku,
            request.quantity,
            rule_applied,
            settings.version,
        )
        return pricing_pb2.PriceOrderResponse(
            total_amount_cents=total_amount_cents,
            discount_cents=discount_cents,
            rule_applied=rule_applied,
            served_by=settings.version,
        )


class _HealthHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        # Route access logging through our structured logger instead of stderr.
        log.info("http %s", format % args)

    def _respond_json(self, status: int, payload: dict[str, str]) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - required BaseHTTPRequestHandler override name
        if self.path == "/healthz":
            self._respond_json(200, {"status": "ok"})
        elif self.path == "/readyz":
            if ready_event.is_set():
                self._respond_json(200, {"status": "ready"})
            else:
                self._respond_json(503, {"status": "not-ready"})
        elif self.path == "/metrics":
            body = generate_latest()
            self.send_response(200)
            self.send_header("Content-Type", CONTENT_TYPE_LATEST)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self._respond_json(404, {"status": "not found"})


def serve() -> None:
    grpc_server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    pricing_pb2_grpc.add_PricingServicer_to_server(PricingServicer(), grpc_server)
    grpc_server.add_insecure_port(f"[::]:{settings.grpc_port}")
    grpc_server.start()
    ready_event.set()

    http_server = HTTPServer(("", settings.http_port), _HealthHandler)
    http_thread = threading.Thread(target=http_server.serve_forever, daemon=True)
    http_thread.start()

    log.info(
        "pricing started version=%s grpc_port=%d http_port=%d",
        settings.version,
        settings.grpc_port,
        settings.http_port,
    )

    stop_event = threading.Event()

    def handle_sigterm(signum: int, frame: FrameType | None) -> None:
        log.info("received signal %d, shutting down", signum)
        stop_event.set()

    signal.signal(signal.SIGTERM, handle_sigterm)
    signal.signal(signal.SIGINT, handle_sigterm)

    stop_event.wait()

    ready_event.clear()
    grpc_server.stop(grace=5).wait()
    http_server.shutdown()
    log.info("pricing stopped")


def main() -> None:
    serve()


if __name__ == "__main__":
    main()

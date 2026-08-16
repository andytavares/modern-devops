from fastapi.testclient import TestClient

from ${{ values.name | replace("-", "_") }}.main import METRIC_PREFIX, SERVICE, app, healthz

client = TestClient(app)


def test_healthz_needs_no_dependencies():
    """Liveness must answer without any downstream, or an outage kills every pod."""
    assert healthz()["status"] == "ok"


def test_routes_are_registered():
    """The chart's probes and prometheus.io annotations depend on these three."""
    paths = {r.path for r in app.routes}
    assert {"/healthz", "/readyz", "/metrics"} <= paths


def test_readyz_reports_ready():
    assert client.get("/readyz").json() == {"status": "ready"}


def test_metrics_endpoint_is_prometheus_formatted():
    body = client.get("/metrics").text
    assert f"{METRIC_PREFIX}_requests_total" in body


def test_metric_prefix_is_a_valid_prometheus_name():
    """Service names are hyphenated; metric names may not be."""
    assert "-" not in METRIC_PREFIX
    assert METRIC_PREFIX.replace("_", "").isalnum()


def test_root_reports_the_service_name():
    assert client.get("/").json()["service"] == SERVICE

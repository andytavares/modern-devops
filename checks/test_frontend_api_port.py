"""The frontend's proxy port must match the port order-api's Service publishes.

These two facts live in different directories, in different languages, and
nothing connects them:

    frontend/nginx.conf                          proxy_pass ...:80/orders
    deploy/charts/order-platform/.../order-api   port: 80

When they disagreed, the dashboard showed `HTTP 502` for every order while
`curl` against the same API returned `202` — because the frontend was proxying
to 8000, order-api's *container* port, which nothing serves on the ClusterIP.
Every instinct sends you to look at order-api, which is fine.

Nothing else in the build can catch this: the chart is valid, the nginx config
is valid, both images build, and every pod is Ready.
"""

import re
from pathlib import Path

REPO = Path(__file__).parent.parent
NGINX_CONF = REPO / "frontend" / "nginx.conf"
SERVICE_TEMPLATE = (
    REPO / "deploy" / "charts" / "order-platform" / "templates" / "order-api.yaml"
)


def _proxied_port() -> int:
    match = re.search(
        r"proxy_pass\s+http://order-api\.shop\.svc\.cluster\.local:(\d+)/",
        NGINX_CONF.read_text(),
    )
    assert match, f"no order-api proxy_pass found in {NGINX_CONF.name}"
    return int(match.group(1))


def _service_port() -> int:
    # The Service is the last document in the template and declares its ports
    # inline: `- { name: http, port: 80, targetPort: http }`.
    body = SERVICE_TEMPLATE.read_text().split("kind: Service")[-1]
    match = re.search(r"name:\s*http,\s*port:\s*(\d+)", body)
    assert match, "no `name: http` port found on the order-api Service"
    return int(match.group(1))


def test_frontend_proxies_to_the_published_service_port():
    proxied, published = _proxied_port(), _service_port()
    assert proxied == published, (
        f"frontend/nginx.conf proxies to order-api:{proxied}, but the Service "
        f"publishes {published}. Every order will return HTTP 502 while order-api "
        f"itself answers normally."
    )

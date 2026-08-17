"""Render the chart and check the things `helm lint` cannot see.

`helm lint --strict` validates structure. It does not know that a probe naming
a port no container declares will crash-loop the pod, because both halves are
individually valid YAML. That defect renders clean, lints clean, and is only
visible once the kubelet tries to resolve the name.

Run against a rendered chart, which is what Helm's own template-debugging guide
prescribes — never against the templates as text, where `{{ }}` hides the value
you are trying to check.

    helm template order-platform deploy/charts/order-platform \\
        -f deploy/env/local/values.yaml -n shop | python3 checks/verify_chart.py -
"""

import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - CI installs it; local runs may not
    sys.exit("pyyaml is required: pip install pyyaml")


def _probe_port_names(container):
    """Every port *name* (not number) this container's probes refer to."""
    out = []
    for key in ("livenessProbe", "readinessProbe", "startupProbe"):
        probe = container.get(key)
        if not probe:
            continue
        for kind in ("httpGet", "tcpSocket"):
            port = (probe.get(kind) or {}).get("port")
            if isinstance(port, str):
                out.append((key, port))
    return out


def check(docs):
    problems = []
    for doc in docs:
        if not doc or doc.get("kind") not in {
            "Deployment",
            "StatefulSet",
            "DaemonSet",
            "Job",
        }:
            continue
        name = doc["metadata"]["name"]
        spec = doc["spec"]["template"]["spec"]
        for container in spec.get("containers", []):
            declared = {p["name"] for p in container.get("ports", []) if "name" in p}
            for probe_kind, port_name in _probe_port_names(container):
                if port_name not in declared:
                    problems.append(
                        f"{doc['kind']}/{name}: {container['name']}.{probe_kind} "
                        f"targets port {port_name!r}, which the container does not "
                        f"declare (declared: {sorted(declared) or 'none'})"
                    )

    # A Service targetPort given by name must exist on the pods it selects.
    ports_by_selector = {}
    for doc in docs:
        if not doc or doc.get("kind") not in {"Deployment", "StatefulSet", "DaemonSet"}:
            continue
        labels = doc["spec"]["template"]["metadata"].get("labels", {})
        names = {
            p["name"]
            for c in doc["spec"]["template"]["spec"].get("containers", [])
            for p in c.get("ports", [])
            if "name" in p
        }
        key = labels.get("app.kubernetes.io/name")
        if key:
            ports_by_selector.setdefault(key, set()).update(names)

    for doc in docs:
        if not doc or doc.get("kind") != "Service":
            continue
        selector = (doc["spec"].get("selector") or {}).get("app.kubernetes.io/name")
        if selector is None or selector not in ports_by_selector:
            continue
        available = ports_by_selector[selector]
        for port in doc["spec"].get("ports", []):
            target = port.get("targetPort")
            if isinstance(target, str) and target not in available:
                problems.append(
                    f"Service/{doc['metadata']['name']}: port {port.get('name')!r} "
                    f"targets {target!r}, which no selected pod declares "
                    f"(declared: {sorted(available) or 'none'})"
                )
    return problems


def check_frontend_proxy_port(docs, repo):
    """The frontend's nginx proxy_pass must target order-api's Service port.

    These two facts live in different directories, in different languages, and
    nothing connects them. When they disagreed, every order in the dashboard
    read `HTTP 502` while curl against the same API returned `202` — the
    frontend was proxying to 8000, order-api's *container* port, which nothing
    serves on the ClusterIP.

    Checked here, against the rendered chart, because the port is a template
    expression in the source and reading it as text means reading `{{ }}`.
    """
    conf = Path(repo) / "frontend" / "nginx.conf"
    if not conf.exists():
        return []
    m = re.search(
        r"proxy_pass\s+http://order-api\.shop\.svc\.cluster\.local:(\d+)/",
        conf.read_text(),
    )
    if not m:
        return ["frontend/nginx.conf: no order-api proxy_pass found"]
    proxied = int(m.group(1))

    for doc in docs:
        if not doc or doc.get("kind") != "Service":
            continue
        if doc["metadata"]["name"] != "order-api":
            continue
        for port in doc["spec"].get("ports", []):
            if port.get("name") == "http":
                if int(port["port"]) != proxied:
                    return [
                        f"frontend/nginx.conf proxies to order-api:{proxied}, but the "
                        f"Service publishes {port['port']}. Every order returns HTTP 502 "
                        f"while order-api itself answers normally."
                    ]
                return []
    return ["no order-api Service with a named `http` port in the rendered chart"]


def main():
    source = (
        sys.stdin if len(sys.argv) > 1 and sys.argv[1] == "-" else open(sys.argv[1])
    )
    docs = list(yaml.safe_load_all(source.read()))
    repo = Path(__file__).parent.parent
    problems = check(docs) + check_frontend_proxy_port(docs, repo)
    for p in problems:
        print("  " + p)
    print(f"chart port consistency: {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

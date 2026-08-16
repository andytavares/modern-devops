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

import sys

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
        if not doc or doc.get("kind") not in {"Deployment", "StatefulSet", "DaemonSet", "Job"}:
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


def main():
    source = sys.stdin if len(sys.argv) > 1 and sys.argv[1] == "-" else open(sys.argv[1])
    problems = check(list(yaml.safe_load_all(source.read())))
    for p in problems:
        print("  " + p)
    print(f"chart port consistency: {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

---
type: tool
tags: [networking, edge]
role: the plain edge for every non-meshed UI, and the hop in front of the Istio gateway
version: controller-v1.13.0
docs: https://kubernetes.github.io/ingress-nginx/
date_added: 2026-08-17
date_updated: 2026-08-17
status: in-use
---

# ingress-nginx

> [!info] One-liner
> Owns `hostPort` 80/443 on the kind control-plane node. It serves the platform's own UIs directly, and hands everything meshed to `istio-ingressgateway` as an ordinary backend.

## What it does here

Installed from the **kind-specific** manifest (§4.3), which makes the controller a Deployment whose
container declares `hostPort` 80 and 443. Combined with kind's `extraPortMappings`, that is what puts
nginx on your laptop's port 80 — **but only if the pod lands on the node those mappings belong to.**

```bash
kubectl -n ingress-nginx patch deployment ingress-nginx-controller --type=strategic -p \
  '{"spec":{"template":{"spec":{"nodeSelector":{"kubernetes.io/os":"linux","ingress-ready":"true"}}}}}'
```

> [!warning] This patch is required, not optional
> controller-v1.13.0's kind manifest **dropped** the `ingress-ready` nodeSelector. It only *tolerates*
> the control plane; it does not require it. Without the patch the controller can land on a worker,
> bind `hostPort` 80 there, and be unreachable from your laptop. The symptom is
> `curl http://localhost` returning **`000`** — nothing listening — which reads like a 404 problem and
> is not (Appendix B).

## Its role after the mesh arrives, which is the subtle part

nginx is **not** the mesh boundary and is deliberately **not enrolled** in [[istio]] (§9.3). The chain
is `nginx (hostPort 80/443) → istio-ingressgateway → mesh workloads` (§9.1). Istio documents two ways
into a mesh — its own Gateway, or an `Ingress` with `ingressClassName: istio` — and enrolling a
third-party controller is neither.

`deploy/platform/istio/edge-ingress.yaml` is the whole of nginx's involvement: a **wildcard-host**
Ingress for `*.localtest.me` pointing at the gateway's Service, with **no annotations**. `istio-system`
has no STRICT `PeerAuthentication`, so the gateway accepts that plaintext hop exactly as it would from
a cloud load balancer, and mTLS begins at the gateway — which has a real workload identity
(`cluster.local/ns/istio-system/sa/istio-ingressgateway`) that the authorization policies key on.

**Exact host beats wildcard.** [[argo-cd]], [[grafana]], [[kiali]], [[backstage]] and
[[sonatype-nexus]] all sit under `localtest.me` and all keep their own exact-host Ingresses, so nginx
routes them straight to their own Services and they never reach the gateway (§9.4). That precedence is
what lets one wildcard serve the whole mesh — and it is also the rule to remember before adding an
exact-host Ingress for a hostname you *meant* to route into the mesh, because that one wins too.

## Two Ingresses cannot claim the same host and path

The nginx admission webhook rejects it outright. §9.4 therefore deletes the `order-api` and `frontend`
Ingresses the chart created in §10.1, and routing for those two moves to `VirtualService`. Same rule
put the frontend on `app.localtest.me` rather than `shop.localtest.me` (§19.4).

## The other nginx in this repo

`frontend/nginx.conf` is a *different* nginx — the one inside the frontend image, serving the [[vite]]
bundle and proxying `/orders` to order-api. It must target the **Service** port (`80`), not the
container port (`8000`); pointing it at 8000 makes every order in the dashboard read `HTTP 502` while
a direct `curl` returns `202`. `checks/verify_chart.py` asserts the two agree — see [[order-platform]].
`nginx-unprivileged` also needs writable `/tmp`, `/var/cache/nginx` and `/var/run`, the same class of
runtime-only failure as [[pex]]'s `PEX_ROOT`.

## Related

[[kind]] · [[istio]] · [[kubernetes]] · [[service-mesh]] · [[order-platform]]

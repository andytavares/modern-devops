---
type: tool
tags: [networking, edge]
role: The cluster edge — every browser-facing URL enters here
version: controller-v1.13.0 (kind variant manifest)
docs: https://kubernetes.github.io/ingress-nginx/
date_added: 2026-08-15
date_updated: 2026-08-16
status: in-use
---

# ingress-nginx

> [!info] One-liner
> An Ingress controller that turns `Ingress` objects into nginx config — the single front door for every `*.localtest.me` URL.

## What it does here

Installed from the **kind-specific** manifest, which runs the controller as a DaemonSet with
`hostPort` 80/443 and a `nodeSelector` of `ingress-ready=true` — the label [[kind]] sets on the
control-plane node (§4.3). The two files must agree or nothing serves.

Routes: `shop.` → order-api, `argocd.` → Argo CD, `grafana.` → Grafana, `kiali.` → Kiali,
`backstage.` → Backstage.

**It is enrolled in the mesh** (§9.3). That is not decoration: with STRICT mTLS in `shop`, an
un-enrolled nginx would send plaintext to order-api and every page load would become a connection
reset. Enrolled, it terminates the browser's connection and re-originates it as mTLS. See [[istio]].

## Key concepts

- **`*.localtest.me` resolves to 127.0.0.1 from public DNS.** Real hostname-based routing, zero
  `/etc/hosts` edits. There is no service behind the domain; it is just a wildcard A record.
- **`ingressClassName`** selects which controller owns an Ingress. Ours is `nginx`.
- Ingress is feature-frozen upstream in favour of the **Gateway API**; new capability lands there.

## Why this, not the alternative

Kept as the edge rather than replaced by an Istio gateway (§9.1) because it already owns `hostPort`
80/443 via kind's fixed port mappings — swapping means rewriting every `Ingress` as an `HTTPRoute`
*and* recreating the cluster. In a greenfield build, a single mesh-native edge is the cleaner answer.

## Gotchas

- Port mappings are fixed at cluster creation; you cannot move the edge without a rebuild.
- A 404 from `curl localhost` right after install is correct — nginx is up with no matching Ingress.
- **It is a `Deployment`, not a `DaemonSet`.** The kind provider manifest ships one replica pinned by
  `nodeSelector` with `hostPort` 80/443. `kubectl rollout restart daemonset/ingress-nginx-controller`
  fails with `NotFound` — which matters most in §13.2, where a missed restart means nginx never gets
  its [[istio]] sidecar and STRICT mTLS turns every page load into a connection reset. The tutorial
  said `daemonset/` in two places until 2026-08-15.

> [!warning] **In-mesh with STRICT mTLS, an Ingress needs two annotations or every page load
> fails.** Observed 2026-08-16 on `app.localtest.me` and `shop.localtest.me`, both returning
> `upstream connect error or disconnect/reset before headers. reset reason: connection termination`
> while all nine pods were `2/2 Running` and Argo reported `Synced`/`Healthy`.
>
> Two independent mismatches, and fixing only one changes nothing:
>
> 1. **NGINX proxies to pod IPs, not the Service.** The controller resolves endpoints and balances
>    across `10.244.1.222:8000` directly. [[istio]] identifies destinations by service; a bare
>    endpoint IP names none, so the sidecar has nothing to originate mTLS *to*.
>    → `nginx.ingress.kubernetes.io/service-upstream: "true"` replaces the endpoint list with a
>    single ClusterIP endpoint ([confirmed in `controller.go`](https://github.com/kubernetes/ingress-nginx/blob/main/internal/ingress/controller/controller.go),
>    `getServiceClusterEndpoint`).
> 2. **NGINX preserves the client's `Host:`.** Envoy routes HTTP by authority, not address, so the
>    request still says `app.localtest.me` — which matches no mesh service. Envoy sends it to
>    `PassthroughCluster` as plaintext, and the destination sidecar resets it.
>    → `nginx.ingress.kubernetes.io/upstream-vhost: "<svc>.<ns>.svc.cluster.local"`.
>
> The diagnosis that ends the argument is in the source sidecar's stats — `destination_service_name`
> reads `PassthroughCluster` with `response_flags.UC` while broken:
>
> ```bash
> kubectl -n ingress-nginx exec deploy/ingress-nginx-controller -c istio-proxy -- \
>   pilot-agent request GET 'stats?filter=istio_requests_total' | grep -o 'destination_service_name\.[A-Za-z-]*'
> ```
>
> And a `200` is **not** proof of the fix — it only proves bytes moved. Check the destination
> reporter for `connection_security_policy.mutual_tls` with a real `source_principal`
> (`spiffe://cluster.local/ns/ingress-nginx/sa/ingress-nginx`). Fixed in the chart for `order-api`,
> `frontend` **and** the scaffolded-service template, since otherwise every paved-path service
> ([[paved-paths]]) ships broken.

## Official docs

- Docs: https://kubernetes.github.io/ingress-nginx/
- Releases: https://github.com/kubernetes/ingress-nginx/releases
- Gateway API: https://gateway-api.sigs.k8s.io/

> [!tip] Related
> [[kind]], [[kubernetes]], [[istio]], [[service-mesh]]

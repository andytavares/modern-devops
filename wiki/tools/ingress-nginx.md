---
type: tool
tags: [networking, edge]
role: The cluster edge — every browser-facing URL enters here
version: controller-v1.13.0 (kind variant manifest)
docs: https://kubernetes.github.io/ingress-nginx/
date_added: 2026-08-15
date_updated: 2026-08-15
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

## Official docs

- Docs: https://kubernetes.github.io/ingress-nginx/
- Releases: https://github.com/kubernetes/ingress-nginx/releases
- Gateway API: https://gateway-api.sigs.k8s.io/

> [!tip] Related
> [[kind]], [[kubernetes]], [[istio]], [[service-mesh]]

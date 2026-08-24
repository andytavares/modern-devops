---
type: tool
tags: [service-mesh, security, networking]
role: mTLS, identity-based authorization, L7 telemetry, and the edge
version: 1.30.3 (charts base + istiod + gateway)
docs: https://istio.io/latest/docs/
date_added: 2026-08-17
date_updated: 2026-08-23
status: in-use
---

# Istio

> [!info] One-liner
> An Envoy proxy beside every pod, giving each hop mutual TLS, identity-based authorization and L7 metrics without touching application code — plus the routing language the canary is written in.

## What it is

`istiod` configures data-plane proxies. In **sidecar** mode an Envoy is injected into each pod and
iptables redirects the pod's traffic through it. The proxy holds a short-lived X.509 certificate
encoding a **SPIFFE identity** derived from the pod's ServiceAccount —
`cluster.local/ns/<ns>/sa/<name>`. Everything else follows from that identity. See [[mtls]].

## What it secures here, and what it honestly does not (§9.1)

The usual mesh demo has service A calling service B. Until [[pants]] brings `pricing`, **this platform
does not have that shape** — order-api never calls order-worker, [[apache-kafka]] joins them.

| Path | In the mesh? |
|---|---|
| browser → nginx → `istio-ingressgateway` | no — nginx is outside; the gateway is the boundary |
| gateway → `order-api`, `frontend` | yes |
| `order-api` → `pricing` (gRPC) | yes — the first synchronous hop, and only from §19 |
| `order-api` / `order-worker` → [[floci]] | yes |
| `order-api` → Kafka | no |
| Prometheus → app `/metrics` | no — and §9.6 is that problem |

The honest pitch: identity-based mTLS on every HTTP hop inside the boundary, an authorization policy
that survives a stolen pod IP, and L7 telemetry for calls whose code you do not control — the AWS
SDK's calls to Floci being the interesting case.

## Installed as three charts, not `istioctl install` (§9.2)

`base` (CRDs, cluster-scoped RBAC), `istiod` (control plane), `gateway` (one edge proxy). Splitting
them is what makes upgrades controllable: CRDs move independently, a gateway rolls without touching
the control plane, and either rolls back alone. `istioctl install` hides those seams — fine for a
demo, wrong for anything you intend to upgrade.

`service.type=ClusterIP` on the gateway, because nothing on [[kind]] hands out load balancers and
[[ingress-nginx]] reaches it in-cluster by Service name anyway.

**The gateway pod runs one Envoy, not two.** The chart ships `image: auto` plus the pod label
`sidecar.istio.io/inject: "true"` and annotation `inject.istio.io/templates: gateway`, so istiod's
webhook renders a standalone proxy. That per-pod opt-in is why `istio-system` itself stays
un-enrolled.

## Enrolment, where the decisions are the exclusions (§9.3)

Enrolled: `shop`, `floci`. Not enrolled: `ingress-nginx` (not the boundary), `kafka` (broker
discovery), `buildkite` (Jobs), `argocd`/`monitoring`/`istio-system` (control plane — injecting your
delivery and observability tooling means an Istio misconfiguration can remove the tools you would use
to diagnose it).

> [!warning] Put `istio-injection: enabled` in the namespace manifest in git, never on the command line
> Once a namespace is under [[argo-cd]], every field of it is. A hand-set label is dropped the next
> time Argo recreates the namespace, and the pods come back **1/1 with no sidecar** — STRICT mTLS then
> rejects them and the PodMonitor matches nothing. `deploy/platform/floci.yaml` and
> `deploy/platform/secret-store.yaml` both carry the label with that reasoning inline.

## The edge (§9.4)

`deploy/platform/istio/edge-gateway.yaml` — a `Gateway` in `istio-system` accepting `*.localtest.me`
on port 80, plus one `VirtualService` per hostname in `shop`.

**`gateways: [istio-system/edge]` in `namespace/name` form** because the Gateway lives in
`istio-system` while the routes live in `shop`. A bare name resolves in the VirtualService's own
namespace and matches nothing — presenting as a **404 from a gateway that looks correctly
configured.**

**The wildcard host is the property worth having.** A service the paved path adds becomes reachable by
declaring a `VirtualService` and nothing else: no edit to the Gateway, no edit to the Ingress, no new
object at the edge. A hostname with no VirtualService gets a 404, which is the correct answer for a
route nobody declared. See [[paved-paths]].

## Proving mTLS is actually on

> [!warning] A `200` proves only that bytes moved
> Plaintext through `PassthroughCluster` returns `200` too. Ask the **destination** sidecar which
> policy it applied — source-side stats report `connection_security_policy.unknown` even on healthy
> mTLS, so checking the wrong reporter looks like a broken mesh.

```bash
kubectl -n shop exec deploy/order-api -c istio-proxy -- \
  pilot-agent request GET 'stats?filter=istio_requests_total' \
  | grep reporter.destination | grep -o 'connection_security_policy\.[a-z_]*'
# connection_security_policy.mutual_tls
```

`mutual_tls` with `source_principal` reading
`spiffe://cluster.local/ns/istio-system/sa/istio-ingressgateway` is the evidence.

> [!warning] Sidecars are injected as **native** sidecars on Kubernetes 1.29+
> They appear as `initContainers` with `restartPolicy: Always`, so `.spec.containers` shows only the
> app and reads exactly like injection failed. `READY 2/2` is the signal to trust.

## Authorization, and why an empty spec matters (§9.5)

**Deny-by-default is a property of a namespace, not of the workloads you wrote a policy for.** A
workload that **no** `ALLOW` policy selects accepts traffic from anything in the mesh. So a file of
per-workload `ALLOW` policies is not default-deny — it is default-deny for the workloads you
remembered. `deploy/platform/istio/authorization-policy.yaml` therefore carries an empty-spec
`deny-all` in *both* `floci` and `shop`, then one ALLOW per real caller relationship.

`order-worker` gets no policy at all, and that is correct: it takes no inbound traffic, and Prometheus
reaches the sidecar's merged endpoint rather than the application.

> [!warning] The ServiceAccount names in `principals` are load-bearing
> They must match the ServiceAccounts the chart creates and — for the gateway — the `istio/gateway`
> chart's ServiceAccount, which takes the Helm **release name**. Install under a different name and the
> policy denies the edge, presenting as `RBAC: access denied` on every page load. `istioctl analyze -n
> shop` catches it; `kubectl get pods` does not.

## Port names are an Istio interface

The grammar is `protocol[-suffix]`: `http`, `http-metrics`, `grpc-pricing`. `metrics-http` is **not**
valid — order matters. A name Istio does not recognise falls back to **automatic protocol detection**,
which sniffs opening bytes per connection, is wrong for anything server-speaks-first, and is flagged as
[IST0118](https://istio.io/latest/docs/reference/config/analysis/ist0118). Lose HTTP and you lose the
L7 features you installed a mesh for. `appProtocol` does the same job explicitly and wins where both
are set. `pricing`'s gRPC port **must** be named `grpc` — there is no `grpc:` stanza in a
`VirtualService`, gRPC rides HTTP/2 and is routed by the ordinary `http:` block. See [[port-naming]].

## Traffic management (§9.9, §9.10)

`deploy/platform/istio/pricing-traffic.yaml` — a `DestinationRule` naming `v1`/`v2` subsets on the
pod label `version`, plus a `VirtualService` weighting 90/10. The retry envelope arithmetic and the
outlier-detection defaults that had to change are on [[timeouts-and-retries]].

`pricing-fault-injection.yaml.disabled` injects a 3s delay into 50% of calls. **The `.disabled` suffix
is the safety mechanism** — Argo CD's manifest glob does not match it, so the file is reviewed and
version-controlled and never applied by the reconciler. *A chaos experiment GitOps can apply on its own
is one that will eventually apply itself on a Friday.*

## The mode not taken

**Sidecar over ambient.** Sidecars cost one extra container and ~50–100 MB per pod plus a restart of
every workload to enroll. Ambient replaces per-pod sidecars with one `ztunnel` per node at a fraction
of the RAM, at the price of needing an explicit waypoint proxy before any L7 policy works. Sidecars
are taken here because the mental model matches the documentation you will hit everywhere else — and
§1.3 says ambient is the better choice if you are RAM-constrained.

## `istioctl analyze` has a non-empty expected baseline, and that is the interesting part

Observed 2026-08-23 at §9.8, on a correct cluster:

```
Error   [IST0101] (VirtualService shop/frontend) Referenced host not found: "frontend.shop.svc.cluster.local"
Error   [IST0101] (VirtualService shop/pricing)  Referenced host not found: "pricing.shop.svc.cluster.local"
Warning [IST0127] (AuthorizationPolicy shop/allow-ingress-to-frontend)   No matching workloads ... name=frontend
Warning [IST0127] (AuthorizationPolicy shop/allow-order-api-to-pricing)  No matching workloads ... name=pricing
Warning [IST0174] (DestinationRule shop/pricing) The host ... does not match any services in the mesh
Error: Analyzers found issues when analyzing namespace: shop.
```

Nothing is wrong. `frontend` and `pricing` arrive in §17–§19 ([[pants]]/[[grpc]] phase); §9.5's
`deny-all` and §9.9's canary routing are written for them ahead of time, because a default-deny policy
has to be complete *before* enrolment rather than retrofitted after. All five clear when Phase 7
deploys those workloads. Confirmed against the cluster: `shop` held `order-api` and `order-worker`
only, and neither was reported against.

> [!warning] The tool the docs point at for the hardest failure is pre-poisoned
> §9.5 argues — correctly — that `istioctl analyze` is what catches a `principals` typo naming a
> ServiceAccount that does not exist, the failure that denies everything while `kubectl get pods`
> looks perfectly healthy. But it exits **non-zero with five findings when nothing is wrong**, so a
> reader who has not been told the baseline learns to skip the output, and the sixth finding — theirs
> — arrives in a list they have already decided is noise. [[kiali]]'s **Istio Config** tab validates
> the same objects and shows the same five in red.
>
> Record the baseline, alert on the delta. This is the ordinary condition of any linter pointed at a
> system built in stages, and it is worth more as a habit than as a fact about Istio.

## The leftover Ingress that 502s everything, silently

Observed 2026-08-23. Every request to `shop.localtest.me` returned `502 Bad Gateway` while the mesh
was, by every other measure, correct: pods `2/2`, `Gateway` and `VirtualService` applied, gateway pod
healthy, `istioctl analyze` showing only its expected baseline, `connection_security_policy` reporting
`mutual_tls` on the hops that did complete.

`kubectl -n shop get ingress` named it in one line: the Phase 1 `Ingress` for `shop.localtest.me` was
still there, recreated by [[argo-cd]] from `orderApi.ingress.enabled: true` in the chart.

The chain:

1. §9.4 adds a **wildcard** `*.localtest.me` Ingress in `istio-system` pointing at
   `istio-ingressgateway`.
2. The Phase 1 chart still ships an **exact-host** `shop.localtest.me` Ingress pointing at the
   `order-api` Service.
3. Different hosts, so nginx admits both without complaint — **this is not an admission conflict**,
   which is what the docs claimed. The exact host wins, by the same precedence rule that keeps Argo CD
   and Grafana off the gateway.
4. nginx therefore talks to `order-api` **in plaintext, from outside the mesh**. STRICT mTLS refuses
   the connection, nginx has no upstream response, and returns 502.

> [!warning] The route you deleted is not the route that is serving
> Nothing in Phase 4 draws attention to an object created in Phase 1, and every diagnostic you would
> reach for reports health, because the mesh **is** healthy — the request never enters it. Worse, the
> tutorial's own instruction was `kubectl -n shop delete ingress order-api frontend`, an imperative
> delete of an object Argo CD recreates from git within the reconcile window: it works, then stops
> working, with no edit nearby to blame. Same failure as [[argo-cd]]'s `helm upgrade` conflict, in a
> costume that does not raise an error.

Fixed by removing the `ingress:` blocks and their values keys from the chart and **pushing**.
Verified: `kubectl -n shop get ingress` → no resources, `GET /healthz` → **200**, `POST /orders` →
**202**, and both halves of §9.6's check non-zero for the first time —
`orders_received_total` = 41 across 2 series, `istio_requests_total` present with
`connection_security_policy="mutual_tls"` and
`source_principal="spiffe://cluster.local/ns/istio-system/sa/istio-ingressgateway"`.

## Related

[[service-mesh]] · [[mtls]] · [[kiali]] · [[ingress-nginx]] · [[prometheus]] · [[port-naming]] · [[timeouts-and-retries]] · [[grpc]] · [[observability]]

---
type: tool
tags: [service-mesh, security, networking]
role: mTLS, authorization and L7 telemetry between pods
version: 1.30.3 (charts base + istiod)
docs: https://istio.io/latest/docs/
date_added: 2026-08-15
date_updated: 2026-08-16
status: in-use
---

# Istio

> [!info] One-liner
> A service mesh: an Envoy proxy beside every pod, giving every hop mutual TLS, identity-based authorization and L7 metrics without touching application code.

## What it is

A control plane (`istiod`) that configures data-plane proxies. In **sidecar** mode an Envoy container
is injected into each pod and iptables redirects the pod's traffic through it. The proxy holds a
short-lived X.509 certificate encoding a **SPIFFE identity** derived from the pod's ServiceAccount —
`cluster.local/ns/<ns>/sa/<name>`. Everything else follows from that identity.

## What it does here — and what it honestly doesn't

The usual mesh demo has service A calling service B. **We don't have that shape**: order-api never
calls order-worker; [[apache-kafka]] joins them (§9.1). What Istio actually covers:

| Path | In the mesh |
|---|---|
| ingress-nginx → order-api | yes (nginx is enrolled, so it can re-originate as mTLS) |
| order-api → [[floci]] (S3) | yes |
| order-worker → Floci (DynamoDB) | yes |
| order-api → Kafka | no — TCP passthrough; brokers advertise listeners, sidecars break discovery |
| Prometheus → app metrics | no — see the merged-metrics workaround |

Enrolled: `shop`, `floci`, `ingress-nginx`. Excluded deliberately: `kafka`, `buildkite` (Jobs),
`argocd`, `monitoring`, `istio-system` (§9.3).

## Key objects

| Object | Answers |
|---|---|
| `PeerAuthentication` | *Must* callers use mTLS? `STRICT` in `shop` and `floci` (§9.4) |
| `AuthorizationPolicy` | *May* this identity make this call? Empty spec = deny-all (§9.5) |
| `DestinationRule` / `VirtualService` | Routing, retries, timeouts, traffic shifting |
| `Sidecar` | Scope of config pushed to a proxy; also the secure-metrics listener |

## Ports worth memorising

| Port | Purpose |
|---|---|
| 15006 | inbound capture (where STRICT is enforced) |
| 15001 | outbound capture |
| **15020** | agent telemetry — **merged** app + Envoy metrics, plaintext under STRICT |
| 15090 | Envoy-only stats (`http-envoy-prom`) |
| 15021 | health |

## Key concepts

- **Identity, not IP.** Policies key on the SPIFFE principal in the peer's certificate. An attacker
  with a shell in another pod cannot mint a certificate for `sa/order-api`. This is why mesh authz and
  NetworkPolicy are complements, not competitors — one filters requests by identity, the other packets
  by address.
- **PERMISSIVE is a migration setting, not a destination.** It accepts plaintext, which is what you're
  trying to eliminate.
- **Injection happens at pod creation.** Labelling a namespace does nothing to running pods; you must
  restart them. And it enrolls *everything* born there, including Jobs.

## Sidecar vs ambient

We chose sidecars: deepest documentation, and `VirtualService`/`DestinationRule` work with no extra
hop. Cost: +1 container and ~50–100 MB **per pod**, plus a restart to enroll. **Ambient** mode
replaces sidecars with one `ztunnel` per node — far cheaper on a laptop — at the price of needing an
explicit waypoint proxy before any L7 policy works. RAM-constrained? Ambient.

## Gotchas

- `kubectl port-forward` into a STRICT namespace fails (`Connection reset by peer`) — it delivers
  plaintext from outside the mesh. Run clients inside instead (§6.4).
- A policy naming a ServiceAccount that doesn't exist denies everything and looks perfectly healthy in
  `kubectl get pods`. `istioctl analyze -n shop` is what catches it.
- Jobs + sidecars = pods that never complete. Annotate `sidecar.istio.io/inject: "false"`.
- `base` and `istiod` must be the same version; Istio supports a narrow Kubernetes window.
- **Namespace enrolment must live in git, not in `kubectl label`.** If [[argo-cd]] manages the
  `Namespace` object, it recreates it without any label you applied by hand — pods come back `1/1`,
  STRICT rejects their traffic, [[kiali]] goes empty and the `PodMonitor` matches nothing, all with no
  error printed. Put `istio-injection: enabled` in the manifest (hit 2026-08-16).
- **Drain the data plane before removing the control plane** — uninstalling `istiod` while sidecars run
  leaves proxies on last-known config that fail closed on restart.

## Official docs

- Docs: https://istio.io/latest/docs/
- Install with Helm: https://istio.io/latest/docs/setup/install/helm/
- PeerAuthentication: https://istio.io/latest/docs/reference/config/security/peer_authentication/
- AuthorizationPolicy: https://istio.io/latest/docs/reference/config/security/authorization-policy/
- Prometheus integration: https://istio.io/latest/docs/ops/integrations/prometheus/
- Secure metrics: https://istio.io/latest/docs/tasks/observability/metrics/secure-metrics/
- Ambient mode: https://istio.io/latest/docs/ambient/

## Open questions

- Is Istio 1.30's native-sidecar support (Kubernetes ≥1.29) enabled by default? It would make Jobs in
  enrolled namespaces safe, and the tutorial deliberately does not assert either way.
- What does enrolling `monitoring` actually cost, versus the merged-metrics approach we took?

> [!tip] Related
> [[service-mesh]], [[mtls]], [[kiali]], [[prometheus]], [[ingress-nginx]], [[floci]], [[kubernetes]]

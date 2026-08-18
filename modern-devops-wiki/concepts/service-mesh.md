---
type: concept
tags: [networking, security, observability]
date_added: 2026-08-17
date_updated: 2026-08-17
---

# Service mesh

> [!info] One-liner
> Move identity, encryption, retries, routing and L7 telemetry out of every application and into a proxy beside it. What you get depends entirely on the shape of your traffic — and this platform's shape is unusual.

## Start with the uncomfortable part

The usual mesh demo has service A calling service B over HTTP, and mTLS between them is the punchline.
**Until Phase 7 this platform does not have that shape.** order-api never calls order-worker;
[[apache-kafka]] joins them, asynchronously and deliberately. Install a mesh here expecting the demo
and you get an expensive no-op (§9.1).

What [[istio]] actually secures and observes here: identity-based [[mtls]] on every HTTP hop inside the
boundary, an authorization policy that survives a stolen pod IP, and **L7 telemetry for calls whose
code you do not control** — the AWS SDK's calls to [[floci]] being the interesting case, since you get
per-route latency and error rates without touching either service.

`pricing` (§19) is the first synchronous service-to-service hop in this platform, **which is what makes
retries, timeouts, traffic shifting and outlier detection mean anything at all.**

## What a mesh cannot see

**Your entire async path.** [[kiali]] draws no edge between order-api and order-worker, because Kafka is
outside the mesh and there is no synchronous call for a proxy to observe.

> **A service graph is not an architecture diagram.** It shows synchronous calls the proxies saw.

The corollary matters when you are debugging: an empty graph and a broken install look identical, and
a missing edge may mean "no traffic", "not meshed", or "joined by something the mesh cannot see".

## Mesh vs NetworkPolicy — not competing answers

NetworkPolicy filters **packets by address**. Istio filters **requests by cryptographic identity**. An
attacker with a shell in another namespace cannot mint a certificate for `sa/order-api`, but nothing in
this platform restricts packets. **Use both.** Appendix C names default-deny NetworkPolicies as a real
gap and is explicit that they are complementary, not a substitute.

With one caveat specific to this cluster: **the CNI here is `kindnetd`, which does not enforce
NetworkPolicy at all**, so a policy written today would apply cleanly and do nothing. Closing that gap
means changing the CNI first — see [[cni]].

## The costs, all of which this repo pays

- **RAM.** One Envoy per pod, ~50–100 MB, plus `istiod` at ~500 MB. Most of a gigabyte on this
  platform. Ambient mode (one `ztunnel` per node) is the better laptop choice if you are constrained;
  sidecars are taken because the mental model matches the documentation you hit everywhere else.
- **A restart of every workload** to enroll it. Sidecars are injected at pod **creation**.
- **Jobs stop completing.** The single most common way a mesh rollout goes wrong: enrolling a namespace
  enrolls everything born in it, including Jobs, CronJobs and one-shot migration pods. **The blast
  radius of `kubectl label namespace` is larger than it looks.**
- **Your monitoring breaks, silently.** See [[observability]] and §9.6.
- **Debugging from outside gets harder, on purpose.** `kubectl port-forward` stops working under
  STRICT. The fix is to bring your tools inside the mesh, not to poke holes.

## Where the boundary goes

Istio documents two ways into a mesh: its own **Gateway**, or an `Ingress` with
`ingressClassName: istio`. **Enrolling a third-party ingress controller is not one of them**, and
Istio's ingress documentation does not mention third-party controllers at all.

So the chain is `nginx → istio-ingressgateway → mesh workloads`. mTLS begins at the gateway, which is a
meshed workload with a real identity — and that identity is the principal the authorization policies
key on. **[[ingress-nginx]] is never told the mesh exists.** North-south and east-west routing then
live in one language, one API, one place to read the whole picture.

## Related

[[istio]] · [[mtls]] · [[cni]] · [[kiali]] · [[observability]] · [[apache-kafka]] · [[ingress-nginx]] · [[timeouts-and-retries]] · [[port-naming]]

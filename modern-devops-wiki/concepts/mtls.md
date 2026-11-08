---
type: concept
tags: [security, networking, identity]
date_added: 2026-08-17
date_updated: 2026-08-17
---

# mTLS and workload identity

> [!info] One-liner
> Both ends of every connection present a certificate. The certificate encodes a SPIFFE identity derived from the pod's ServiceAccount, so authorization keys on *who you are* rather than *where you are*.

## Why identity beats network position

`cluster.local/ns/shop/sa/order-api` is a name an attacker cannot forge without the private key. An IP
address is a thing that can be stolen, reused, or reassigned by the scheduler.

`kubectl -n shop run rogue --image=curlimages/curl ... → RBAC: access denied` is the demonstration
(§15.4): **that pod is in the mesh and holds a valid certificate, and is still refused**, because its
identity is `sa/default`. Compare with a stolen-IP attack: there is nothing to steal.

## PERMISSIVE is a migration setting, not a destination

Istio defaults to PERMISSIVE — accepting both mTLS and plaintext, so nothing breaks when you enroll a
namespace. **A workload that accepts plaintext is a workload an attacker can talk to in plaintext.**
`deploy/platform/istio/peer-authentication.yaml` sets STRICT in `shop` and `floci`.

## Deny-by-default is a property of a *namespace*

Istio's rule: a workload that **no** `ALLOW` policy selects accepts traffic from anything in the mesh.
So a file containing nothing but per-workload `ALLOW` policies is **not** default-deny — it is
default-deny for the workloads you remembered, and wide open for the rest.

The empty-spec `deny-all` per namespace is what makes the phrase true, and it must exist in `shop` for
the same reason it exists in `floci`:

```yaml
kind: AuthorizationPolicy
metadata: { name: deny-all, namespace: shop }
spec: {}     # An empty spec with no rules is a deny-all. This is not a typo.
```

`order-worker` gets no ALLOW policy at all, and that is correct: it takes no inbound traffic, and
Prometheus reaches the sidecar's merged endpoint rather than the application.

## Proving it, which is not the same as it working

> [!warning] A `200` proves only that bytes moved
> Plaintext through `PassthroughCluster` returns `200` too. And **source-side stats report
> `connection_security_policy.unknown` even on healthy mTLS**, so checking the wrong reporter looks
> like a broken mesh.

Read the **destination** reporter and look for `connection_security_policy.mutual_tls` plus a real
`source_principal`. In [[kiali]], the padlock on an edge is the same fact drawn.

## The failure it produces when something is outside the mesh

`upstream connect error … reset reason: connection termination` is **not a dead backend** — it is a
refused unauthenticated connection. The diagnostic that names it precisely is the source sidecar's
`istio_requests_total` reporting `destination_service_name.PassthroughCluster` with
`connection_security_policy.unknown`: the mesh could not identify the destination, which is what a
caller outside the mesh looks like.

The same mechanism is why `kubectl port-forward` to [[floci]] stops working after §9.4 — and that is
the correct behaviour, not a regression.

## Certificate lifecycle is the part you do not operate

istiod issues short-lived certificates to every proxy and rotates them. Nobody in this tutorial issues
a certificate by hand, and that is the value proposition: **identity is a property of the platform, not
of your services.** No application code knows mTLS exists — which is also why
`grpc.aio.insecure_channel` is correct in order-api's pricing client, since TLS in the application
would be a redundant second layer.

## What is still plaintext

The browser → nginx hop, [[sonatype-nexus]], and [[openbao]]. Appendix C: cert-manager for issuance,
then real certificates on the ingress and on Nexus.

## Related

[[istio]] · [[service-mesh]] · [[kiali]] · [[floci]] · [[grpc]] · [[secrets-management]] · [[observability]]

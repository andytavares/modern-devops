---
type: concept
tags: [security, identity]
docs: https://spiffe.io/docs/latest/spiffe-about/overview/
date_added: 2026-08-15
date_updated: 2026-08-15
---

# mTLS and workload identity

> [!info] One-liner
> Both sides present certificates, so every call carries a verifiable identity — and authorization stops depending on network position.

## The idea

Ordinary TLS authenticates the *server*. Mutual TLS authenticates both, so the callee knows who is
calling, cryptographically. In a mesh the identity is a **SPIFFE ID** derived from the pod's
ServiceAccount:

```
cluster.local/ns/shop/sa/order-api
```

Certificates are short-lived and rotated by the control plane. Nothing is in your application code.

## Why this beats network-based authorization

An attacker who lands a shell in some other pod gets an IP, and an IP is worthless here — they cannot
mint a certificate for `sa/order-api`. That is the difference between "the network says you're
trusted" and "you proved who you are".

Concretely, in this platform (§9.5): [[floci]] denies everything by default and allows exactly two
principals. A pod in the mesh with a valid certificate but the wrong identity is still refused
(§15.4 ⑥).

## Practical consequences

- **STRICT vs PERMISSIVE**: PERMISSIVE accepts plaintext too. It is a migration setting; leaving it on
  means an attacker can simply speak plaintext.
- **Everything that talks to a STRICT namespace must be in the mesh** — including your ingress
  controller, or every page load becomes a connection reset.
- **Plaintext tooling breaks**: `port-forward`, external scrapers, ad-hoc `curl` from outside.
- **ServiceAccounts become load-bearing**. If your chart doesn't create them, every pod is
  `sa/default` and identity-based policy is meaningless.

## Official docs

- SPIFFE overview: https://spiffe.io/docs/latest/spiffe-about/overview/
- Istio PeerAuthentication: https://istio.io/latest/docs/reference/config/security/peer_authentication/
- Istio AuthorizationPolicy: https://istio.io/latest/docs/reference/config/security/authorization-policy/

> [!tip] Related
> [[istio]], [[service-mesh]], [[kubernetes]], [[secrets-management]]

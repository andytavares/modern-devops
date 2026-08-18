---
type: concept
tags: [networking, kubernetes]
docs: https://kind.sigs.k8s.io/docs/user/configuration
date_added: 2026-08-17
date_updated: 2026-08-17
---

# CNI — the Container Network Interface

> [!info] One-liner
> Kubernetes does not implement pod networking. It states a contract and delegates the work to a plugin. The CNI is that plugin interface.

## The contract

Kubernetes requires:

- every pod gets its own IP address
- every pod can reach every other pod **without NAT**
- nodes can reach pods, and pods can reach nodes

It does not say how. A CNI plugin satisfies the contract by doing three things when a pod is created:
allocate it an IP, wire its network namespace to the node, and arrange routing so packets reach pods on
*other* nodes. Swap the plugin and the contract is unchanged — which is the point of having an
interface.

The CNI operates on **packets and addresses**. That is the whole reason it is a different layer from
[[mtls]], which operates on requests and cryptographic identity.

## What this platform uses

**`kindnetd`**, [[kind]]'s built-in default, entirely unconfigured. `infra/kind-cluster.yaml` has no
`networking:` block, so kind's defaults apply — pod subnet `10.244.0.0/16`
(https://kind.sigs.k8s.io/docs/user/configuration, as of 2026-08).

Nothing in `docs/` mentions the CNI, and nothing needs to: it is the one piece of cluster
infrastructure here that required no decision. That is worth stating rather than leaving implicit,
because it is also the reason for the gap below.

Replacing it is one field, which kind documents as an advanced feature with limited support:

```yaml
networking:
  disableDefaultCNI: true    # then install Calico, Cilium, etc. yourself
```

## The consequence: NetworkPolicy is inert here

> [!warning] `kindnetd` does not enforce NetworkPolicy
> A `NetworkPolicy` object applies cleanly on this cluster and **does nothing.** Nothing errors,
> nothing warns, and `kubectl get networkpolicy` shows it present.

Appendix C lists default-deny NetworkPolicies as a real gap and is right to — but closing it is not
"write a NetworkPolicy". It is **change the CNI first**, to one that enforces them (Calico, Cilium),
and then write the policy. Reading the gap the other way produces a policy that reads as security and
provides none.

This is the same class of failure as [[timeouts-and-retries]]' `maxEjectionPercent` rounding to zero: a
feature that reports as configured and never fires.

## Why it is not a substitute for the mesh, and vice versa

| | Filters | Identity is | Sees |
|---|---|---|---|
| CNI / NetworkPolicy | **packets**, by address and port | an IP or a label selector | everything on the wire, including non-HTTP |
| [[istio]] | **requests**, by SPIFFE identity | a certificate | only what its proxies are in the path of |

An IP can be stolen or reassigned; a certificate cannot be forged. But the mesh only sees traffic
through its sidecars — a workload outside the mesh is unconstrained by it, which is exactly what
NetworkPolicy would cover. **Use both**, which is Appendix C's position and [[service-mesh]]'s.

Note what that means concretely here: [[apache-kafka]] is outside the mesh by choice, so nothing at all
restricts who may open a TCP connection to a broker.

## Related

[[kind]] · [[kubernetes]] · [[service-mesh]] · [[istio]] · [[mtls]] · [[apache-kafka]] · [[timeouts-and-retries]]

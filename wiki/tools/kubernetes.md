---
type: tool
tags: [orchestration, core]
role: The runtime everything else is built on
version: whatever kind v0.32.0 ships (Istio 1.30 supports ~1.32–1.36)
docs: https://kubernetes.io/docs/home/
date_added: 2026-08-15
date_updated: 2026-08-15
status: in-use
---

# Kubernetes

> [!info] One-liner
> A control loop engine: you declare desired state as API objects, and controllers work continuously to make reality match.

## What it is

An API server backed by etcd, plus a set of controllers that reconcile. That framing matters more
than "container orchestrator", because almost every tool in this platform is *also* a controller
doing the same trick on its own object type — [[argo-cd]] reconciles Applications, [[strimzi]]
reconciles Kafka clusters, [[external-secrets-operator]] reconciles ExternalSecrets. Learn the
reconciliation pattern once and the rest of the stack stops looking like fifteen separate products.

The unit of scheduling is the **Pod** (one or more co-located containers sharing a network namespace).
Everything else — Deployment, Service, Ingress — exists to manage Pods or route to them.

## What it does here

Runs as a three-node [[kind]] cluster named `devops` (§4). Namespaces are the platform's structural
boundary, and the tutorial draws each one where a *cluster* boundary would sit in production (§1.3):

| Namespace | Holds | In the mesh? |
|---|---|---|
| `shop` | order-api, order-worker, scaffolded services | yes |
| `floci` | the AWS emulator | yes |
| `ingress-nginx` | the edge | yes |
| `kafka` | Strimzi operator + brokers | no (§9.3) |
| `argocd`, `monitoring`, `buildkite`, `istio-system`, `backstage`, `openbao`, `external-secrets` | control plane | no |

## Key concepts

- **Declarative, not imperative.** `kubectl apply` states intent; a controller does the work, forever.
- **Labels and selectors** are the join keys of the whole system. A Service finds Pods by label; a
  [[prometheus]] PodMonitor finds Pods by label; a ServiceAccount is how [[istio]] finds *identity*.
- **ServiceAccount = workload identity.** This is why the chart gives order-api and order-worker their
  own SAs (§10.1) — Istio's authorization policies key on them, and `default` is not an identity.
- **Jobs are not Deployments.** They terminate. That single fact breaks sidecars (§9.3) and is worth
  internalising before you enroll a namespace in a mesh.

## Gotchas

- `kubectl port-forward` delivers **plaintext from outside the mesh**, so it stops working against
  namespaces with STRICT mTLS (§6.4). Not a bug — the workaround is to run the client inside.
- `kubectl edit` is temporary once [[argo-cd]] has `selfHeal: true`. Disable sync deliberately during
  an incident rather than fighting the controller.
- Env vars are set at container start: changing a Secret does **not** change a running Pod (§15.4).

## Official docs

- Docs home: https://kubernetes.io/docs/home/
- API reference: https://kubernetes.io/docs/reference/kubernetes-api/
- Gateway API (the successor to Ingress): https://gateway-api.sigs.k8s.io/

## Open questions

- What k8s version does kind 0.32.0 actually pin, and is it inside Istio 1.30's support window?

> [!tip] Related
> [[kind]], [[helm]], [[argo-cd]], [[istio]], [[containerd]], [[reconciliation]]

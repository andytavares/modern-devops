---
type: concept
tags: [kubernetes, architecture]
docs: https://kubernetes.io/docs/concepts/architecture/controller/
date_added: 2026-08-15
date_updated: 2026-08-15
---

# Reconciliation (the control loop)

> [!info] One-liner
> Declare desired state; a controller observes actual state and acts, continuously, forever. Almost every tool here is an instance of this one pattern.

## The pattern

```
loop:
  desired = read spec from the API
  actual  = observe the world
  if actual != desired: act
  record status
```

It is **level-triggered**, not edge-triggered: a controller doesn't react to events so much as
repeatedly notice a difference. That is why it survives missed events, restarts and partial failures —
and why "did the webhook fire?" is usually the wrong question.

## Every one of these is the same trick

| Controller | Desired state | Acts on |
|---|---|---|
| Deployment controller | replica count, pod template | Pods |
| [[argo-cd]] | a git revision | any Kubernetes object |
| [[strimzi]] | a `Kafka` resource | StatefulSets, PVCs, certs, rolling restarts |
| [[external-secrets-operator]] | an `ExternalSecret` | Kubernetes Secrets |
| [[istio]] (`istiod`) | policies and routes | Envoy proxy config |

Learn it once and the stack stops looking like fifteen unrelated products.

## What it implies for you

- **Status is a first-class read.** `.status.conditions` is where a controller tells you why it can't
  reach desired state. `Degraded` on a missing image tag is honest reporting, not a bug.
- **Manual changes are transient** wherever something is reconciling (`selfHeal: true`).
- **One-shot Jobs are the anti-pattern.** They create and stop. Nothing notices drift, and the
  manifest in git can be a lie ten minutes later — exactly the criticism of our infra paved path
  (§14.7), where the production answer is a reconciled resource (Crossplane / ACK).

## Official docs

- Controllers: https://kubernetes.io/docs/concepts/architecture/controller/
- Operator pattern: https://kubernetes.io/docs/concepts/extend-kubernetes/operator/

> [!tip] Related
> [[kubernetes]], [[argo-cd]], [[strimzi]], [[external-secrets-operator]], [[gitops]]

---
type: concept
tags: [kubernetes, operations, patterns]
docs: https://kubernetes.io/docs/concepts/architecture/controller/
date_added: 2026-08-17
date_updated: 2026-08-17
---

# Reconciliation

> [!info] One-liner
> Declare desired state; a controller continuously observes actual state and acts to close the gap. It is the one pattern behind almost every tool in this platform.

## The loop

```
observe actual → diff against desired → act → repeat, forever
```

Three properties fall out, and they are why the pattern won:

- **Level-triggered, not edge-triggered.** The controller does not need to have seen the event. It
  compares current state, so a missed message, a restart or a manual change all self-correct on the
  next pass.
- **Idempotent by construction.** Acting when there is no gap is a no-op, so retrying is free.
- **Convergent, not transactional.** It does not promise the change happened *now*; it promises the
  system trends towards the declaration.

## Every controller in this repo is the same shape

| Controller | Desired state | Actual state |
|---|---|---|
| [[kubernetes]] Deployment controller | `replicas: 2` | running pods |
| [[argo-cd]] | a git revision | live objects |
| [[strimzi]] | `Kafka`, `KafkaNodePool`, `KafkaTopic` | brokers, quorum, PVCs, topics |
| [[external-secrets-operator]] | `ExternalSecret` | a Kubernetes `Secret` |
| Prometheus Operator | `PodMonitor`, `PrometheusRule` | scrape config, alert rules |
| [[istio]] istiod | `PeerAuthentication`, `VirtualService` | Envoy config on every proxy |

Learn it once and every operator you meet afterwards is a variation.

## Where this platform *breaks* the pattern, and says so

**The [[backstage]] `new-bucket` paved path emits a one-shot Job, not a custom resource.** It creates
the bucket and stops. It will not notice if someone deletes it, it cannot express "make the bucket look
like this", and there is no drift detection — the manifest in git can be a lie ten minutes after it
merges. The production answer is a provider that reconciles: Crossplane, or the AWS Controllers for
Kubernetes, where an `S3Bucket` custom resource is continuously reconciled against the real thing.

> **If you take one idea from §14.7 into a real platform, take that one: paved paths should produce
> declarative resources, not one-shot jobs.**

**The cluster itself is imperative.** `kind create cluster` is a command, not a manifest. Appendix C
names it a real gap.

## The operational consequence people underestimate

`selfHeal: true` means **`kubectl edit` is temporary.** Argo reverts your change within seconds, and it
will infuriate you the first time you are debugging live. That is the correct default; the escape hatch
is `argocd app set <app> --sync-policy none` for the duration of an incident. Reach for it
consciously, rather than fighting the controller.

## Related

[[gitops]] · [[argo-cd]] · [[strimzi]] · [[external-secrets-operator]] · [[istio]] · [[kubernetes]] · [[paved-paths]]

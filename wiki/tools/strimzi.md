---
type: tool
tags: [kafka, operator, kubernetes]
role: Runs and reconciles Kafka on Kubernetes
version: 0.50.1 (Kafka 4.1.0)
docs: https://strimzi.io/docs/operators/latest/overview
date_added: 2026-08-15
date_updated: 2026-08-16
status: in-use
---

# Strimzi

> [!info] One-liner
> The reference Kubernetes operator for Kafka — you declare a `Kafka` resource, it owns the StatefulSets, PVCs, certificates and rolling restarts.

## What it is

An operator that turns Kafka's operational knowledge into a control loop. The value is not that it
creates a StatefulSet — you could — it is that it knows **how to restart a broker safely**: check
in-sync replicas, drain, roll one at a time, wait for the ISR to recover. That is the part that is
hard to write and dangerous to get wrong.

## What it does here

Installed via Helm into `kafka`, then a `Kafka` + `KafkaNodePool` + `KafkaTopic` declared in
`deploy/platform/kafka.yaml` (§8.3). Takes 3–5 minutes to converge: PVCs bind, controllers form a
quorum, brokers join.

## Key concepts

- **`KafkaNodePool`** separates controller and broker roles into independently scalable pools — the
  modern Strimzi topology.
- **`KafkaTopic` as a CRD** means topics are GitOps-managed like everything else, not created by an
  ad-hoc CLI call nobody remembers running.
- **Operator, not StatefulSet** (§8.1): the generalisable lesson is that stateful systems on
  Kubernetes want an operator, and "I'll just write a StatefulSet" is how you learn why.

## Why this, not the alternative

Apache Kafka is Apache-2.0 — the broker is free. What costs money is **someone operating it for you**:
Amazon MSK, Confluent Cloud, or **Confluent for Kubernetes**, the licensed operator Confluent sells to
do approximately what Strimzi does. Strimzi is the CNCF project filling that slot for nothing, which is
the same substitution this platform makes with [[openbao]] for Vault and [[sonatype-nexus]] CE for
Artifactory.

**Not an option:** using the AWS emulator's MSK. [[floci]] advertises `kafka` and answers
`list-clusters`, but `create-cluster` 500s because that family of emulator launches a real broker as a
sibling Docker container through `/var/run/docker.sock` — which a pod does not have. See [[floci]].

**What transfers if your employer runs managed Kafka:** topics, partitions, keys, consumer groups,
rebalancing, `acks=all` with `min.insync.replicas`, and offset-commit ordering. All of it.

**What does not:** broker operations — rolling upgrades, node-pool sizing, watching the operator
rebuild a broker. That is exactly what the managed services sell. Read §8 as *understanding what the
managed service does on your behalf*. The `KafkaTopic` CRD is the piece that goes either way:
topic-as-code is worth wanting wherever the brokers live.

## Gotchas

- **Strimzi 0.46+ is KRaft-only**; 0.50 is the last release supporting Kubernetes 1.27–1.29. Operators
  encode compatibility matrices — read them before upgrading either side.
- Do **not** inject Istio sidecars into broker pods (§9.3). Strimzi has its own TLS and listener
  story; use that instead.
- Pods `Pending` is usually PVC/disk, not Kafka.

> [!warning] Deleting the `Kafka` CR before its `KafkaTopic`s deadlocks them permanently
> Hit 2026-08-15. `KafkaTopic` carries the finalizer `strimzi.io/topic-operator`, and only the **topic
> operator** can remove it. The topic operator runs inside the entity-operator, which is part of the
> `Kafka` cluster — so deleting the `Kafka` CR first destroys the only party able to release the
> finalizer. The topic then hangs in `Terminating` forever. The **cluster operator** does not help;
> it doesn't own topic finalizers.
>
> This wedged an [[argo-cd]] cascade delete for ~80 minutes: `KafkaTopic/orders` was the lone
> "1 objects remaining for deletion" blocking two Applications, which in turn blocked everything else
> in the platform from being recreated.
>
> Unblock by clearing the unsatisfiable finalizer — not a hack, since its owner no longer exists:
>
> ```bash
> kubectl -n kafka patch kafkatopic orders --type=merge -p '{"metadata":{"finalizers":[]}}'
> ```
>
> Both Applications finished terminating within ten seconds. **Order matters on teardown: topics
> before cluster.**

## Official docs

- Overview: https://strimzi.io/docs/operators/latest/overview
- Configuring (CRD reference): https://strimzi.io/docs/operators/latest/configuring
- Releases: https://github.com/strimzi/strimzi-kafka-operator/releases

> [!tip] Related
> [[apache-kafka]], [[kraft]], [[kubernetes]], [[reconciliation]]

---
type: tool
tags: [messaging, operator]
role: the operator that runs Kafka safely on Kubernetes
version: 0.50.1 (Kafka 4.1.0)
docs: https://strimzi.io/docs/operators/latest/overview
date_added: 2026-08-17
date_updated: 2026-08-17
status: in-use
---

# Strimzi

> [!info] One-liner
> A Kubernetes operator that turns `Kafka`, `KafkaNodePool` and `KafkaTopic` custom resources into a managed cluster. The canonical example of [[reconciliation]] applied to stateful software.

## Why an operator and not a StatefulSet

Write the StatefulSet yourself and you own broker ID assignment, rolling restarts that respect
in-sync replica counts, certificate rotation, partition rebalancing on scale-up, and [[kraft]]
controller quorum management. That is a full-time job. Strimzi encodes it as controller logic — which
is what operators are *for*: stateful software with non-trivial day-2 operations (§8.1).

## What it does here

Installed with `watchAnyNamespace=false`, scoping it to `kafka` only. Cluster-wide watching is
convenient and is also how one team's malformed CR takes down another team's cluster (§8.2).

`deploy/platform/kafka.yaml` declares two node pools — a 3-replica `controller` quorum and a 3-replica
`broker` pool — plus the `Kafka` and the `orders` `KafkaTopic`. Separating controllers from brokers is
the recommended production topology: controllers hold metadata and want stable low-latency nodes,
brokers hold data and scale independently.

The `Kafka` resource carries `strimzi.io/node-pools: enabled` and `strimzi.io/kraft: enabled`.

## Version compatibility is encoded, and you must read it

- **Strimzi 0.46+ is KRaft-only.** 0.45 was the last release supporting ZooKeeper. A tutorial with a
  `zookeeper:` block in the `Kafka` resource is out of date.
- **Strimzi 0.50 is the last release supporting Kubernetes 1.27–1.29** (Appendix A).

Operators encode compatibility matrices. Read them before upgrading either side.

## Failure modes

- **Kafka pods `Pending`** — no PVs or insufficient resources. On [[kind]] the default local-path
  provisioner needs disk; check [[docker]]'s allocation (Appendix B).
- **`kubectl wait kafka/orders` times out** — controllers have not formed a quorum. Read
  `.status.conditions` on the `Kafka`, and `logs orders-controller-0`. Expect 3–5 minutes on first
  create while PVCs bind.
- **Deleting the `Kafka` resource takes the PVCs with it**, because `deleteClaim: true`. A cascade
  delete of the [[argo-cd]] `root` Application therefore destroys the Kafka data. `prune: false` on
  the `platform` Application exists for exactly this blast radius (§11.4).

## Consumer lag, which is the metric that matters

```bash
kubectl -n kafka exec -it orders-broker-0 -- \
  bin/kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
    --describe --group order-worker
```

Not scraped by [[prometheus]] here. `order_event_age_seconds`, exported by order-worker, is the
in-band proxy this platform alerts on instead — see [[observability]].

## Related

[[apache-kafka]] · [[kraft]] · [[reconciliation]] · [[kubernetes]] · [[argo-cd]] · [[prometheus]]

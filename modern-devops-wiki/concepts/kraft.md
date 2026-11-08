---
type: concept
tags: [messaging, architecture]
docs: https://kafka.apache.org/documentation/#kraft
date_added: 2026-08-17
date_updated: 2026-08-17
---

# KRaft

> [!info] One-liner
> Kafka without ZooKeeper. Nodes take `controller` and/or `broker` roles and manage cluster metadata through a Raft quorum among the controllers.

## Why it matters practically

**ZooKeeper is gone.** [[strimzi]] 0.46 and later are **KRaft-only** — 0.45 was the last release
supporting ZooKeeper. If you find a tutorial with a `zookeeper:` block in the `Kafka` resource, it is
out of date (§8.1).

One fewer distributed system to operate, monitor, secure and upgrade. Metadata is now a Kafka log like
everything else, which means metadata operations scale with the same machinery as data.

## The shape here

Two `KafkaNodePool`s (§8.3):

| Pool | Replicas | Role | Storage |
|---|---|---|---|
| `controller` | 3 | metadata quorum | 2Gi |
| `broker` | 3 | data | 5Gi |

Separating them is the recommended production topology: controllers hold metadata and want stable,
small, low-latency nodes; brokers hold data and scale independently.

**The quorum is 3 and it is always odd.** A Raft quorum of 3 tolerates one failure. Even counts buy no
additional fault tolerance and cost a node.

The `Kafka` resource opts in with two annotations:

```yaml
strimzi.io/node-pools: enabled
strimzi.io/kraft: enabled
```

plus `metadataVersion: 4.1-IV0` alongside `version: 4.1.0`. The metadata version is a separate,
forward-only upgrade lever — you move brokers first and the metadata version afterwards.

## Where it fails

`kubectl wait kafka/orders` timing out usually means the controllers have not formed a quorum. Read
`kubectl -n kafka logs orders-controller-0` and `describe kafka orders`'s `.status.conditions`. Expect
3–5 minutes on first create while PVCs bind.

## Related

[[apache-kafka]] · [[strimzi]] · [[kubernetes]]

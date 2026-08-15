---
type: concept
tags: [kafka, architecture]
docs: https://kafka.apache.org/documentation/#kraft
date_added: 2026-08-15
date_updated: 2026-08-15
---

# KRaft (Kafka Raft)

> [!info] One-liner
> Kafka's own Raft-based consensus for cluster metadata, replacing the ZooKeeper dependency.

## What changed

Kafka historically needed a **ZooKeeper** ensemble to store cluster metadata — a second distributed
system to operate, monitor and upgrade. KRaft moves that metadata into Kafka itself, managed by a
quorum of **controller** nodes using Raft.

Practical effects: one system instead of two, faster metadata operations and failover, and a much
larger supported partition count.

## Why it matters here

[[strimzi]] 0.46+ is **KRaft-only**, so this platform runs the modern topology by construction (§8.1)
— you learn the current architecture rather than a legacy one. Controllers and brokers are declared as
separate `KafkaNodePool` resources so they scale independently.

Practical consequence during install: the cluster takes 3–5 minutes to come up because PVCs bind,
**controllers form a quorum**, and only then do brokers join. A `kubectl wait` that times out usually
means the controller quorum hasn't formed — check `orders-controller-0` logs, not the brokers.

## Official docs

- KRaft: https://kafka.apache.org/documentation/#kraft
- Strimzi overview: https://strimzi.io/docs/operators/latest/overview

> [!tip] Related
> [[apache-kafka]], [[strimzi]]

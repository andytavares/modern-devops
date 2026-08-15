---
type: tool
tags: [messaging, events]
role: The event backbone joining order-api to order-worker
version: Kafka 4.1.0 (via Strimzi 0.50.1)
docs: https://kafka.apache.org/documentation/
date_added: 2026-08-15
date_updated: 2026-08-15
status: in-use
---

# Apache Kafka

> [!info] One-liner
> A distributed, replicated, partitioned append-only log — durable messaging where consumers track their own position.

## What it is

Producers append to **topics**, which are split into **partitions**. Each partition is an ordered,
immutable log. Consumers in a **consumer group** each own a subset of partitions and commit their
**offset** — so Kafka doesn't delete on read, it retains, and a consumer can rewind.

The properties that matter architecturally: ordering is per-partition (not per-topic), throughput
scales with partitions, and the maximum useful consumer count equals the partition count.

## What it does here

Topic `orders`, 3 partitions, replication factor 3, `min.insync.replicas: 2` (§8.3). order-api
produces; order-worker consumes as group `order-worker` and writes to DynamoDB.

This is why [[istio]] has less to secure than a mesh demo implies (§9.1): **order-api never calls
order-worker.** They are joined asynchronously by the log, which is outside the mesh — so no service
graph can draw that relationship. A service graph is not an architecture diagram.

## Key concepts

- **KRaft** — Kafka's own Raft-based consensus, replacing ZooKeeper. Strimzi 0.46+ is KRaft-only, so
  this platform runs the modern topology. See [[kraft]].
- **`acks=all` + `min.insync.replicas=2`** means a write is acknowledged only when durably replicated.
  Lose two of three brokers and writes *fail* rather than silently losing data — that is the system
  working (§15.4).
- **Rebalancing**: every consumer-group membership change triggers one. This is why order-worker rolls
  with `maxSurge: 0, maxUnavailable: 1` — surging would cause two rebalances per pod instead of one.
- **Consumer lag** is the health metric that matters: are we falling behind?

## Gotchas

- Replicas > partitions means idle consumers. Keep `replicas <= partitions`.
- Brokers advertise listener addresses; putting an Envoy sidecar in that path breaks discovery, which
  is why the `kafka` namespace is deliberately **not** in the mesh (§9.3).
- Malformed messages are currently dropped — no DLQ. Listed as a known gap.

## Official docs

- Docs: https://kafka.apache.org/documentation/
- KRaft: https://kafka.apache.org/documentation/#kraft
- Consumer groups: https://kafka.apache.org/documentation/#intro_consumers

> [!tip] Related
> [[strimzi]], [[kraft]], [[order-platform]], [[istio]]

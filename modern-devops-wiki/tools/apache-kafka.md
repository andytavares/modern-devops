---
type: tool
tags: [messaging, events]
role: the durable log joining order-api to order-worker
version: 4.1.0 (metadataVersion 4.1-IV0), run by Strimzi 0.50.1
docs: https://kafka.apache.org/documentation/
date_added: 2026-08-17
date_updated: 2026-08-17
status: in-use
---

# Apache Kafka

> [!info] One-liner
> A partitioned, replicated, durable log. order-api produces; order-worker consumes. It is also the reason [[istio]] has no request path to secure between those two services.

## What it does here

One cluster named `orders` in the `kafka` namespace, run by [[strimzi]] — three controllers, three
brokers, [[kraft]] mode. One topic, `orders`: 3 partitions, 3 replicas, `min.insync.replicas: 2`,
7-day retention.

Bootstrap address for other namespaces:
`orders-kafka-bootstrap.kafka.svc.cluster.local:9092`.

## The four settings that are decisions, not defaults (§8.3)

**`auto.create.topics.enable: false`.** With auto-create on, a typo in a topic name silently produces
to a brand-new topic with default settings, and you find out when a consumer reports zero messages.
Off means the typo fails loudly. Declare topics as `KafkaTopic` resources in git — they are config.

**`min.insync.replicas: 2` with `replicas: 3`.** Producers using `acks=all` block until 2 replicas have
the write. Lose one broker: still writable. Lose two: writes **fail** rather than silently
under-replicating. Failing writes is the correct behaviour — the alternative is accepting data you
cannot guarantee. §15.4 has you prove it by deleting brokers.

**3 partitions.** Partition count caps consumer parallelism, so at most 3 useful `order-worker`
replicas in one group — which is why the chart sets `orderWorker.replicas: 2`. You can increase
partitions later but never decrease, and increasing changes key→partition mapping, breaking per-key
ordering for in-flight keys. Size for growth on day one.

**`deleteClaim: true`.** PVCs are deleted with the cluster. Right for a laptop, catastrophic in
production.

## The producer side (order-api)

`acks="all"`, `enable_idempotence=True`, `linger_ms=5`. The default is faster and will silently lose
writes when a broker restarts. **Partition key is the order id**, because Kafka guarantees ordering
only *within* a partition — keying by order id means a later "order cancelled" can never overtake
"order created" (§3.1).

**S3 is written before the Kafka publish.** If the publish fails you have an orphan object — cheap and
recoverable. Published-first with a failed S3 write leaves the worker consuming an event pointing at
an object that does not exist. **Order your side effects so the recoverable failure is the likely
one.**

## The consumer side (order-worker)

The commit-boundary discipline lives on [[franz-go]] and in [[at-least-once-delivery]]. The short
version: an offset is committed only *after* its DynamoDB write succeeded, a failed write blocks the
partition permanently, and `PutItem` on the same `order_id` is idempotent so replay is harmless.

## What Kafka costs this platform

**It is outside the mesh** (§9.3) — Strimzi brokers advertise listener addresses and do their own TLS
and rebalancing, and putting Envoy in that path is a known source of broker-discovery failures for no
security gain. Consequence: **[[kiali]] cannot draw an edge between order-api and order-worker**,
because there is no synchronous call to observe. A service graph is not an architecture diagram — it
shows what the proxies saw, and it is blind to the entire async path (§9.7). See [[service-mesh]].

**Malformed messages are dropped**, not dead-lettered. Appendix C lists a DLQ topic plus an alert on
its rate as the next step.

## Related

[[strimzi]] · [[kraft]] · [[franz-go]] · [[at-least-once-delivery]] · [[go]] · [[fastapi]] · [[service-mesh]]

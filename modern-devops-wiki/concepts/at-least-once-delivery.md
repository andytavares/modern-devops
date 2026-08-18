---
type: concept
tags: [messaging, reliability, data]
date_added: 2026-08-17
date_updated: 2026-08-17
---

# At-least-once delivery, and idempotent writes

> [!info] One-liner
> Do not buy exactly-once delivery. Make your writes idempotent and buy at-least-once, which is cheap.

## The trade

Exactly-once across [[apache-kafka]] and DynamoDB would need transactional coordination the two systems
do not share. What this platform does instead:

- An offset is committed **only after** its DynamoDB write returned success.
- A crash in between replays the record.
- `PutItem` with the same `order_id` **overwrites rather than duplicates**.

So replay is a no-op: at-least-once *delivery* gives effectively-once *results*.

> **The general lesson: don't buy exactly-once delivery; make your writes idempotent and buy
> at-least-once** (§3.2).

The same idea appears twice more in this repo, in places that look unrelated: `|| true` on
`create-bucket` followed by `wait table-exists` (**assert the outcome, tolerate the mechanism**), and
the [[openbao]] operator-auth Job, whose every step — enabling an already-enabled auth method,
rewriting an existing policy or user — is a no-op on re-run.

## The commit boundary is the part that can lose data silently

**A Kafka commit is one offset per partition, not a set of offsets.** Marking any later record commits
past every earlier one — including a record whose write failed. So "mark only on success" is
**necessary and not sufficient**.

The first failed write has to stop the partition dead, and it has to **stay** stopped across polls,
because a mark made on the next batch would commit the record that was never written. That is what
`blocked map[partitionKey]bool` buys. See [[franz-go]] for the client options that make it work.

Two regression tests exist so nobody reintroduces the naive version:

- `TestProcessPartitionNeverMarksAtOrPastAFailedWrite`
- `TestProcessPartitionStaysBlockedOnLaterBatches`

They are possible because `handle` and `processPartition` take two narrow interfaces — `putItemAPI` and
`recordMarker` — rather than the concrete clients. **That is the whole reason a fake can drive a failing
write.**

A revoked partition is deleted from `blocked`, so it starts clean if this member is assigned it again:
the next owner resumes from the offset just committed.

## A malformed record is skipped, and still marked

A message that will never become valid is logged and skipped, because retrying forever pins the
partition — and **not** marking it would pin the commit boundary forever on one bad message. Both are
data-loss-shaped, in opposite directions.

In production that record goes to a **dead-letter topic** instead of the floor. Appendix C lists a DLQ
plus an alert on its rate as the missing piece.

## Ordering, and the durability settings that back it

**Partition key is the order id**, because Kafka guarantees ordering only *within* a partition — so a
later "order cancelled" can never overtake "order created".

`acks="all"` + `enable_idempotence=True` on the producer, `min.insync.replicas: 2` with `replicas: 3`
on the topic. Lose two brokers and writes **fail** rather than silently under-replicating. **Failing
writes is the correct behaviour**; the alternative is accepting data you cannot guarantee.

## Shutdown is part of the guarantee

`OnPartitionsRevoked` fires on group leave, so `client.Close()` commits on SIGTERM — which only happens
because `run() error` has one exit point after the defers rather than an inline `os.Exit`, and because
`terminationGracePeriodSeconds: 45` gives it time. See [[go]] and [[health-checks]].

## Related

[[franz-go]] · [[apache-kafka]] · [[go]] · [[floci]] · [[health-checks]] · [[order-platform]]

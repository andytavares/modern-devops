---
type: tool
tags: [messaging, go, library]
role: order-worker's Kafka client, and the source of its commit semantics
version: v1.21.6
docs: https://github.com/twmb/franz-go
date_added: 2026-08-17
date_updated: 2026-08-17
status: in-use
---

# franz-go

> [!info] One-liner
> A pure-Go Kafka client. Chosen over the alternatives because it needs no cgo, which is what lets order-worker be a static binary in a distroless image.

## Why this client (§3.2)

| Client | Verdict |
|---|---|
| **franz-go** | Pure Go, so `CGO_ENABLED=0` static builds just work. Full modern protocol including [[kraft]]-era features. Actively maintained, large user base. |
| `confluent-kafka-go` | Wraps librdkafka — battle-tested, and drags cgo into your build |
| `segmentio/kafka-go` | Fine, thinner coverage of newer protocol features |

The cgo point is not incidental: [[pants]] sets `[golang] cgo_enabled = false` and
`gcr.io/distroless/static-debian12` has no libc and no dynamic loader. A cgo-linked client would
produce `exec /order-worker: no such file or directory` on a binary that is present and executable.
See [[cross-compilation]].

## The commit strategy, which is the whole point

Three client options that only work as a set (§3.2):

```go
kgo.AutoCommitMarks(),      // autocommit only records handed to MarkCommitRecords
kgo.BlockRebalanceOnPoll(), // a commit can never land on a partition already lost
kgo.OnPartitionsRevoked(…), // flush marked offsets before losing partitions
```

This is franz-go's documented "marks" style, from its `group_committing` and
`goroutine_per_partition_consuming` examples. `OnPartitionsRevoked` fires on **group leave** too,
which is what makes `client.Close()` commit on SIGTERM — and what
`terminationGracePeriodSeconds: 45` in the chart exists to allow time for.

## Why marks, and not "commit what succeeded"

**A Kafka commit is one offset per partition, not a set of offsets.** Marking any later record commits
past every earlier one — including a record whose DynamoDB write failed. So marking only on success is
*necessary and not sufficient*: the first failed write has to stop the partition dead, and it has to
**stay** stopped across polls, because a mark made on the next batch would commit the record that was
never written.

That is what the `blocked map[partitionKey]bool` buys. It needs no lock, because it is read and written
only between `PollFetches` and `AllowRebalance`, and in the revoke callback — which
`BlockRebalanceOnPoll` documents as mutually exclusive.

Two regression tests in `services/order-worker/main_test.go` pin this, driven through the narrow
`putItemAPI` and `recordMarker` interfaces declared at the top of `main.go`:

- `TestProcessPartitionNeverMarksAtOrPastAFailedWrite`
- `TestProcessPartitionStaysBlockedOnLaterBatches`

A malformed record is still **marked**, deliberately — otherwise one bad message pins the partition's
commit forever.

## Related

[[apache-kafka]] · [[at-least-once-delivery]] · [[go]] · [[cross-compilation]] · [[strimzi]]

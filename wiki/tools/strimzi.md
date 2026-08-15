---
type: tool
tags: [kafka, operator, kubernetes]
role: Runs and reconciles Kafka on Kubernetes
version: 0.50.1 (Kafka 4.1.0)
docs: https://strimzi.io/docs/operators/latest/overview
date_added: 2026-08-15
date_updated: 2026-08-15
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

## Gotchas

- **Strimzi 0.46+ is KRaft-only**; 0.50 is the last release supporting Kubernetes 1.27–1.29. Operators
  encode compatibility matrices — read them before upgrading either side.
- Do **not** inject Istio sidecars into broker pods (§9.3). Strimzi has its own TLS and listener
  story; use that instead.
- Pods `Pending` is usually PVC/disk, not Kafka.

## Official docs

- Overview: https://strimzi.io/docs/operators/latest/overview
- Configuring (CRD reference): https://strimzi.io/docs/operators/latest/configuring
- Releases: https://github.com/strimzi/strimzi-kafka-operator/releases

> [!tip] Related
> [[apache-kafka]], [[kraft]], [[kubernetes]], [[reconciliation]]

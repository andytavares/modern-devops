# Wiki index

Every page in this wiki, grouped by the slot it fills in the platform. Start here.

Ask a question with `/wiki-ask`; add a source with `/wiki-ingest`; check for rot with `/wiki-lint`.
The rules live in [`CLAUDE.md`](../CLAUDE.md). The primary source is `modern-devops-tutorial.md`,
whose sections are cited throughout as `§N.M`.

> [!info] Status as of 2026-08-16
> The platform has now been **built and run on a live kind cluster** through §13, and CI executes real
> jobs in-cluster. Seven defects in the tutorial were found by running it and have been fixed; each is
> recorded on the relevant tool page as a `> [!warning]` with the exact symptom. The pages carrying
> observed-in-anger failures are [[sonatype-nexus]], [[buildkite]], [[uv]], [[go]], [[argo-cd]],
> [[strimzi]], [[floci]] and [[ingress-nginx]]. See [[log]] for the sequence.

## How to read this

Each tool page separates **what it is** (vendor capability, rots slowly) from **what it does here**
(local usage, rots fast) and records **why this and not the alternative**. Concept pages cover ideas
that span tools — read those when a question is "why is it like this", not "what is this".

## The platform, in build order

| § | Layer | Pages |
|---|---|---|
| 4 | Cluster | [[kubernetes]], [[kind]], [[containerd]], [[docker]], [[ingress-nginx]] |
| 5 | Artifacts | [[sonatype-nexus]] |
| 6 | Cloud emulation | [[floci]] |
| 7 | Secrets | [[openbao]], [[external-secrets-operator]] |
| 8 | Events | [[apache-kafka]], [[strimzi]] |
| 9 | Service mesh | [[istio]] |
| 10 | Packaging | [[helm]], [[order-platform]] |
| 11 | Delivery | [[argo-cd]] |
| 12 | CI | [[buildkite]], [[buildah]] |
| 13 | Observability | [[prometheus]], [[grafana]], [[kiali]] |
| 14 | Portal | [[backstage]], [[postgresql]] |
| 3 | Applications | [[fastapi]], [[uv]], [[go]] |

## Tools

### Cluster and runtime
- [[kubernetes]] — the control-loop engine everything else is built on
- [[kind]] — the local three-node cluster; real kubelet and containerd in Docker
- [[containerd]] — the node runtime, and the `hosts.toml` that makes Nexus pullable
- [[docker]] — hosts the kind nodes, the Nexus container, and the shared network
- [[ingress-nginx]] — the single edge for every `*.localtest.me` URL

### Artifacts, secrets, state
- [[sonatype-nexus]] — registry plus PyPI/Go/npm proxies; the supply-chain choke point
- [[openbao]] — the source of truth for secrets (Vault's MPL fork)
- [[external-secrets-operator]] — syncs OpenBao values into Kubernetes Secrets
- [[postgresql]] — Backstage's catalog and scaffolder state
- [[floci]] — S3 and DynamoDB locally, no AWS account

### Messaging
- [[apache-kafka]] — the durable log joining order-api to order-worker
- [[strimzi]] — the operator that runs Kafka safely on Kubernetes

### Mesh and networking
- [[istio]] — mTLS, identity-based authorization, L7 telemetry
- [[kiali]] — the mesh made visible, plus Istio config validation

### Delivery
- [[helm]] — packaging, ours and everyone else's
- [[argo-cd]] — pull-based GitOps; CI never touches the cluster
- [[buildkite]] — hybrid CI; SaaS control plane, agents on our infrastructure
- [[buildah]] — daemonless image builds inside CI pods

### Observability
- [[prometheus]] — scraping, storage, alert evaluation
- [[grafana]] — dashboards as code

### Portal and applications
- [[backstage]] — catalog plus the two paved paths
- [[order-platform]] — the app this platform exists to deliver, and its chart
- [[fastapi]] — order-api (Python)
- [[go]] — order-worker
- [[uv]] — Python dependency resolution and locking

## Concepts

- [[reconciliation]] — the control loop; the one pattern behind fifteen tools
- [[gitops]] — git as desired state, pulled and continuously reconciled
- [[immutable-image-tags]] — SHA tags, never `latest`, and why it's a security property
- [[dynamic-pipelines]] — generating CI config instead of committing it
- [[supply-chain-choke-point]] — why an artifact repository is not storage
- [[secrets-management]] — the reference-in-git pattern, and its three timing traps
- [[service-mesh]] — what a mesh gives you, and what it can't see
- [[mtls]] — workload identity, and why it beats network-based authorization
- [[observability]] — what exists, the Istio interaction, and the gaps
- [[paved-paths]] — the rule that makes a golden path actually get used
- [[kraft]] — Kafka without ZooKeeper

## Also here

- [[log]] — append-only record of every wiki operation
- [[open-questions]] — what we don't know yet, and what it would take to find out

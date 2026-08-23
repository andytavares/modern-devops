# Wiki index

Every page in this wiki, grouped by the slot it fills in the platform. Start here.

Ask a question with `/wiki-ask`; add a source with `/wiki-ingest`; check for rot with `/wiki-lint`.
The rules live in [`CLAUDE.md`](../CLAUDE.md). The source is `docs/`, whose sections are cited
throughout as `§N.M`; `modern-devops-tutorial.md` is **assembled** from it and carries the same
numbers, so the two cannot disagree.

> [!info] Status as of 2026-08-17
> **This wiki was rebuilt from scratch on 2026-08-17**, against the current state of `docs/` and of the
> repository. The previous edition — including its `log.md` and `open-questions.md` — was deliberately
> discarded rather than carried forward; it is recoverable from git history
> (`git show 376b4d8:wiki/log.md`). Every page here is derived from the seven phase files, the
> appendices, and the files in the repo. Nothing was copied forward unverified.
>
> **What has actually been run.** The platform was built on a live [[kind]] cluster through §13:
> [[sonatype-nexus]], [[floci]], [[openbao]] + [[external-secrets-operator]], Kafka/[[strimzi]],
> [[istio]] with STRICT mTLS, [[argo-cd]] app-of-apps and [[buildkite]] CI all ran. **[[kiali]],
> [[backstage]] and the [[prometheus]]/[[grafana]] stack (§14–§16) are documented, not observed**, and
> so are the canary and fault-injection drills. Pages carry a `status:` field saying which.
>
> **Where the failures are.** The tutorial reads as one linear path with no sidebars; the diagnostics
> live in Appendix B (organised by *symptom*) and here, as `> [!warning]` callouts on the relevant tool
> page. See [[progressive-build]] for why that division exists and why a listing in `docs/` that
> disagrees with the repo is usually correct.

## How to read this

Each tool page separates **what it is** (vendor capability, rots slowly) from **what it does here**
(local usage, rots fast) and records **why this and not the alternative**. Concept pages cover ideas
that span tools — read those when the question is "why is it like this", not "what is this".

## The platform, in build order

| § | Layer | Pages |
|---|---|---|
| 4 | Cluster | [[kubernetes]], [[kind]], [[containerd]], [[docker]], [[ingress-nginx]] |
| 5 | Artifacts | [[sonatype-nexus]] |
| 6 | Cloud emulation | [[floci]] |
| 7 | Secrets | [[openbao]], [[external-secrets-operator]] |
| 8 | Events | [[apache-kafka]], [[strimzi]], [[franz-go]] |
| 9 | Service mesh | [[istio]], [[kiali]] |
| 10 | Packaging | [[helm]], [[order-platform]] |
| 11 | Delivery | [[argo-cd]] |
| 12 | CI | [[buildkite]], [[buildah]] |
| 13 | Observability | [[prometheus]], [[grafana]] |
| 14 | Portal | [[backstage]], [[postgresql]] |
| 17–19 | Build system | [[pants]], [[pex]], [[grpc]], [[mypy]], [[vite]] |
| 3 | Applications | [[fastapi]], [[pydantic]], [[go]], [[uv]] |

## Tools

### Cluster and runtime
- [[kubernetes]] — the control-loop engine everything else is built on
- [[kind]] — the local three-node cluster; real kubelet and containerd in Docker
- [[containerd]] — the node runtime, and the `hosts.toml` that makes Nexus pullable
- [[docker]] — hosts the kind nodes, the Nexus container, and the shared network
- [[ingress-nginx]] — the plain edge, and the hop in front of the Istio gateway

### Artifacts, secrets, state
- [[sonatype-nexus]] — registry plus PyPI/Go/npm proxies; the supply-chain choke point. Community Edition standing in for Nexus Pro / JFrog Artifactory
- [[openbao]] — the source of truth for secrets; the MPL fork standing in for HashiCorp Vault
- [[external-secrets-operator]] — projects OpenBao values into ordinary Kubernetes Secrets
- [[floci]] — S3 and DynamoDB locally, no AWS account; standing in for LocalStack Pro
- [[postgresql]] — Backstage's catalog and scaffolder state, and the one credential OpenBao does not solely own

### Messaging
- [[apache-kafka]] — the durable log joining order-api to order-worker
- [[strimzi]] — the operator that runs Kafka safely on Kubernetes
- [[franz-go]] — order-worker's client, and the source of its commit semantics

### Mesh and networking
- [[istio]] — mTLS, identity-based authorization, L7 telemetry, and the edge
- [[kiali]] — the mesh made visible, plus Istio config validation (§9.7, moved there from §13.6)

### Delivery
- [[helm]] — packaging, ours and everyone else's
- [[argo-cd]] — pull-based GitOps; CI never touches the cluster
- [[buildkite]] — hybrid CI; SaaS control plane, agents on our infrastructure
- [[buildah]] — daemonless image builds, and a capability list worth reading

### Observability
- [[prometheus]] — scraping, storage, alert evaluation, and the monitor swap
- [[grafana]] — dashboards as code

### Build system
- [[pants]] — one build system for Python, Go and TypeScript; the monorepo's whole argument
- [[pex]] — Python services as one executable zip, so the image is `FROM` plus `COPY`
- [[grpc]] — one `.proto` compiled into two languages; the first synchronous hop in the platform
- [[mypy]] — typechecking, and why generated protobuf needs `.pyi` stubs
- [[vite]] — the Canary Watch dashboard that makes a traffic shift visible in a browser

### Portal and applications
- [[backstage]] — catalog plus the two paved paths
- [[order-platform]] — the app this platform exists to deliver, its chart, and the checks that keep it honest
- [[fastapi]] — order-api, and the shape every scaffolded service copies
- [[pydantic]] — request validation, and config that refuses to start when it is wrong
- [[go]] — order-worker
- [[uv]] — Python dependency resolution and locking; superseded by [[pants]], kept for its lockfile/index lesson

## Concepts

- [[reconciliation]] — the control loop; the one pattern behind fifteen tools
- [[gitops]] — git as desired state, pulled and continuously reconciled
- [[immutable-image-tags]] — SHA tags, never `latest`, and why it is a security property
- [[supply-chain-choke-point]] — why an artifact repository is not storage
- [[dynamic-pipelines]] — generating CI config instead of committing it
- [[secrets-management]] — the reference-in-git pattern, and its three timing traps
- [[service-mesh]] — what a mesh gives you, and what it cannot see
- [[mtls]] — workload identity, and why deny-by-default is a property of a namespace
- [[observability]] — what exists, the Istio interaction, and the gaps
- [[paved-paths]] — the rule that makes a golden path actually get used
- [[kraft]] — Kafka without ZooKeeper
- [[cni]] — how pods get networking at all, and why NetworkPolicy is inert on this cluster
- [[enterprise-substitution]] — why OpenBao, Nexus CE and Floci, and exactly where each stops being equivalent
- [[progressive-build]] — why a listing in `docs/` that disagrees with the repo is usually correct, and the two things `checks/` cannot catch
- [[dependency-inference]] — what Pants infers, and where to stop trusting it
- [[cross-compilation]] — building on one machine and running on another, three ways
- [[port-naming]] — a port name is a load-bearing declaration, read by two systems
- [[health-checks]] — liveness vs readiness, and why channel state is a lie
- [[timeouts-and-retries]] — the retry-envelope arithmetic, and outlier detection's rounding trap
- [[at-least-once-delivery]] — don't buy exactly-once; make your writes idempotent

## Also here

- [[log]] — append-only record of every wiki operation
- [[open-questions]] — what we don't know yet, and what it would take to find out

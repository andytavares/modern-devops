# Wiki index

Every page in this wiki, grouped by the slot it fills in the platform. Start here.

Ask a question with `/wiki-ask`; add a source with `/wiki-ingest`; check for rot with `/wiki-lint`.
The rules live in [`CLAUDE.md`](../CLAUDE.md). The primary source is `modern-devops-tutorial.md`,
whose sections are cited throughout as `§N.M`.

> [!info] Status as of 2026-08-16
> The platform has now been **built and run on a live kind cluster** through §13, and CI executes real
> jobs in-cluster. Defects found by running it are recorded on the relevant tool page as a
> `> [!warning]` with the exact symptom. The pages carrying observed-in-anger failures are
> [[sonatype-nexus]], [[buildkite]], [[uv]], [[go]], [[argo-cd]], [[strimzi]], [[floci]],
> [[ingress-nginx]], [[pants]], [[pex]] and [[vite]]. See [[log]] for the sequence.
>
> **The build system changed on 2026-08-16.** [[pants]] replaced per-language toolchains, one
> `.proto` now generates Python and Go stubs ([[grpc]]), and a third service (`pricing`) runs as a
> two-version [[istio]] canary. §17–§19 in `docs/phase-7-polyglot-monorepo.md`; those sections do not
> exist in the single-document edition yet.
>
> **The tool-choice arguments were reframed on 2026-08-16.** [[floci]], [[openbao]] and
> [[sonatype-nexus]] were previously justified on *licensing*, which read like dodging fees around
> obscure tools. The actual principle — now stated once in §0 and in `docs/README.md` — is that this
> platform is shaped like an **enterprise**, and where the component a real employer hands you is
> behind a price tag or an account gate it is substituted with the open-source equivalent that teaches
> the same lesson. Each of the three pages now names the commercial tool, what it costs, what
> concretely transfers, and **where it does not**.
>
> **The edge was broken the whole time and the platform never said so (2026-08-16).** Every Ingress
> returned `upstream connect error … connection termination` while all nine pods were `2/2 Running`
> and Argo read `Synced`/`Healthy`. [[ingress-nginx]] in the mesh under STRICT mTLS needs *two*
> annotations — `service-upstream` **and** `upstream-vhost` — and fixing one alone does nothing. New
> §9.4 subsection in both editions; full diagnosis on [[ingress-nginx]] and [[istio]].
>
> **Two defects found by running it on 2026-08-16.** A secret written to OpenBao was invisible to the
> cluster for up to an hour while [[external-secrets-operator]] reported `Ready=True` — the escape
> hatch and the two non-leaking diagnostics are now on that page and in [[secrets-management]]. And
> the [[backstage]] catalog was missing `pricing` and `frontend` entirely while declaring a relation
> to an API entity that did not exist; both API entities now have generated, drift-tested definitions.
>
> One documented claim was found to be **false and has been corrected**: `-ldflags "-X
> main.version=…"` never stamped anything, because `main.go` has no such symbol. Both §3.2 and
> [[go]] carried it. See [[go]] for the full record.

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
| 17–19 | Build system | [[pants]], [[pex]], [[grpc]], [[vite]] |
| 3 | Applications | [[fastapi]], [[uv]], [[go]] |

## Tools

### Cluster and runtime
- [[kubernetes]] — the control-loop engine everything else is built on
- [[kind]] — the local three-node cluster; real kubelet and containerd in Docker
- [[containerd]] — the node runtime, and the `hosts.toml` that makes Nexus pullable
- [[docker]] — hosts the kind nodes, the Nexus container, and the shared network
- [[ingress-nginx]] — the single edge for every `*.localtest.me` URL

### Artifacts, secrets, state
- [[sonatype-nexus]] — registry plus PyPI/Go/npm proxies; the supply-chain choke point. Community Edition standing in for Nexus Pro / JFrog Artifactory
- [[openbao]] — the source of truth for secrets; the MPL fork standing in for HashiCorp Vault
- [[external-secrets-operator]] — syncs OpenBao values into Kubernetes Secrets
- [[postgresql]] — Backstage's catalog and scaffolder state
- [[floci]] — S3 and DynamoDB locally, no AWS account; standing in for LocalStack Pro

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

### Build system
- [[pants]] — one build system for Python, Go and TypeScript; the monorepo's whole argument
- [[pex]] — Python services as one executable zip, so the image is `FROM` plus `COPY`
- [[grpc]] — one `.proto` compiled into two languages; the first synchronous hop in the platform
- [[vite]] — the Canary Watch dashboard that makes a traffic shift visible in a browser

### Portal and applications
- [[backstage]] — catalog plus the two paved paths
- [[order-platform]] — the app this platform exists to deliver, and its chart
- [[fastapi]] — order-api (Python)
- [[go]] — order-worker
- [[uv]] — Python dependency resolution and locking (superseded by [[pants]] for building; still the reference for lockfile/index discipline)

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

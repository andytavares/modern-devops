---
type: tool
tags: [cluster, runtime, orchestration]
role: the control-loop engine every other component is built on
version: whatever `kind` v0.32.0 ships; must sit inside Istio 1.30's support window (~1.32–1.36)
docs: https://kubernetes.io/docs/home/
date_added: 2026-08-17
date_updated: 2026-08-17
status: in-use
---

# Kubernetes

> [!info] One-liner
> A set of controllers that watch declared desired state and act to make reality match it. Every other tool here is either a controller, a custom resource, or something a controller manages.

## What it is

An API server backed by etcd, plus controllers that reconcile. You write objects; controllers diff
them against the world and act. That single pattern — [[reconciliation]] — is what
[[argo-cd]], [[strimzi]], [[external-secrets-operator]], [[istio]] and the Prometheus Operator all
are. Learn it once.

## What it does here

Runs on three [[kind]] nodes. The namespaces, and why each is drawn where it is (§1.3 notes that
every namespace boundary here would be a *cluster* boundary in production):

| Namespace | Holds | In the mesh? |
|---|---|---|
| `shop` | order-api, order-worker, pricing v1/v2, frontend, scaffolded services | yes (§9.3) |
| `floci` | [[floci]] and its bootstrap Job | yes |
| `kafka` | [[strimzi]] operator, the `orders` Kafka cluster | no |
| `openbao` | [[openbao]] | no |
| `external-secrets` | [[external-secrets-operator]] | no |
| `istio-system` | istiod, `istio-ingressgateway`, [[kiali]] | no (the gateway opts *itself* in per-pod) |
| `ingress-nginx` | [[ingress-nginx]] | no |
| `argocd` | [[argo-cd]] | no |
| `monitoring` | [[prometheus]], [[grafana]], Alertmanager | no |
| `buildkite` | [[buildkite]] agent-stack-k8s controller and its build Jobs | no |
| `backstage` | [[backstage]] and its [[postgresql]] | no |

## Networking is delegated, not implemented

Kubernetes defines the pod-network contract and hands the work to a **CNI** plugin. On this platform
that is [[kind]]'s built-in `kindnetd`, unconfigured. See [[cni]] for what that does and does not buy
you — the short version is that it satisfies the contract and enforces no NetworkPolicy.

## Things this platform makes you learn the hard way

**A Deployment's `selector` is immutable.** The chart's `op.labels` helper emits the full recommended
label set on every object but keeps `selector.matchLabels` to `app.kubernetes.io/name` alone —
because `helm.sh/chart` changes on every chart bump and a label in a selector can never be edited
without deleting the workload (§10.1). Put in a selector only what you will never need to change.

**`enableServiceLinks: false` on every pod template.** Kubernetes injects a Docker-links relic env
var per Service in the namespace — `PRICING_PORT=tcp://10.96.x.y:50051`. An app reading a variable of
that name as its own config gets a URL where it expected an integer, and env vars outrank every other
config source, so the app cannot win. Every Deployment in `deploy/charts/order-platform/templates/`
turns it off.

**`hostPort` is a property of a node, not a cluster.** Anything reached through a fixed host port
must be *pinned* to the node publishing it. Tolerating that node is not pinning it — see
[[ingress-nginx]] (§4.3).

**Jobs and classic sidecars do not mix.** A sidecar keeps running after the job container exits, so
the pod never reaches `Completed`. Every Job in this repo carries
`sidecar.istio.io/inject: "false"` on its **pod template** (§9.3). Kubernetes ≥1.29 native sidecars
(`initContainers` with `restartPolicy: Always`) fix this and [[istio]] uses them for ordinary pods —
which is separately confusing, because `.spec.containers` then shows only the app.

**A `grpc:` probe's `port` is an `int32`, not an `IntOrString`.** A port *name* is rejected by the API
server. `pricing`'s probes name the number (§19.3). See [[health-checks]].

**`kubectl apply --dry-run=server` validates schema, not whether the process can start.** A probe
naming a port no container declares, or a PEX with nowhere to write, renders clean, lints clean, and
fails only at runtime. That gap is why `checks/verify_chart.py` exists — see [[order-platform]].

## Related

[[kind]] · [[cni]] · [[containerd]] · [[reconciliation]] · [[helm]] · [[argo-cd]] · [[istio]]

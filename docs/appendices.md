# Appendices

[← All phases](README.md) · [← Phase 6 — Operating it, and taking it down](phase-6-operating.md)

Reference material shared by every phase: pinned versions verified against a running cluster, the
symptom-first troubleshooting table, what this platform deliberately does not do, and a flat command
reference.

---

## Appendix A — Version matrix

Verified 2026-08-16 against a running cluster — every version below was read back from the live workload or the installed chart, not from a changelog. Re-check before you start; these move.

| Component | Version | How to check |
|---|---|---|
| kind | v0.32.0 | `kind version` / [releases](https://github.com/kubernetes-sigs/kind/releases) |
| Helm | ≥ 3.8.0 (OCI required) | `helm version --short` |
| ingress-nginx | controller-v1.13.0 | [releases](https://github.com/kubernetes/ingress-nginx/releases) — **note:** v1.13.0's kind manifest dropped the `ingress-ready` nodeSelector; [§4.3](phase-0-foundations.md#43-install-the-ingress-controller) patches it back |
| Sonatype Nexus | `sonatype/nexus3:3.95.0` | [Docker Hub tags](https://hub.docker.com/r/sonatype/nexus3/tags) |
| Floci | `floci/floci:1.5.11` | [github.com/floci-io/floci](https://github.com/floci-io/floci) |
| OpenBao Helm chart | 0.29.1 (OpenBao 2.5.0) | `helm search repo openbao/openbao --versions` |
| External Secrets Operator | chart 2.6.0 | `helm search repo external-secrets/external-secrets --versions` |
| Strimzi | 0.50.1 (Kafka 4.1.0) | `helm search repo strimzi/strimzi-kafka-operator --versions` |
| Argo CD | v3.4.7 | [releases](https://github.com/argoproj/argo-cd/releases) |
| agent-stack-k8s | 0.46.3 | [releases](https://github.com/buildkite/agent-stack-k8s/releases) |
| kube-prometheus-stack | 88.3.0 (Prometheus Operator v0.93.0) | `helm search repo prometheus-community/kube-prometheus-stack --versions` |
| Istio (`base`, `istiod`) | 1.30.3 | `helm search repo istio/istiod --versions` |
| Kiali (`kiali-server`) | 2.30.0 | `helm search repo kiali/kiali-server --versions` |
| Backstage chart | 2.10.0 (`create-app` 1.53.1) | `helm search repo backstage/backstage --versions` |
| Node.js | 22.x or 24.x (Active LTS) | `node --version` |
| Yarn | 4.18.0 — whatever `create-app` pins in `packageManager`; **never downgrade** ([§14.3](phase-5-developer-portal.md#143-scaffold-the-portal)) | `yarn --version` |
| Buildah | `quay.io/buildah/stable:v1.40.1` | [quay.io tags](https://quay.io/repository/buildah/stable?tab=tags) |
| Go | 1.26.x | `go version` |
| Python | 3.13.x | `python3 --version` |
| FastAPI | 0.139.2 | `uv pip list` |
| uv | 0.12.x | `uv --version` |

Two version rules worth internalising:

- **Pin everything in git; upgrade deliberately.** `latest` on any of the above turns a routine `kubectl apply` into an unplanned upgrade.
- **Strimzi 0.50 is the last release supporting Kubernetes 1.27–1.29**, and **Strimzi 0.46+ is KRaft-only**. Operators encode version compatibility matrices; read them before upgrading either side.
- **Istio supports a narrow window of Kubernetes versions** (1.30.x covers roughly 1.32–1.36) and expects `base` and `istiod` to be at the same version. A mesh where the CRDs and the control plane disagree fails in ways that look like application bugs.

---

## Appendix B — Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `ImagePullBackOff` on `nexus:8082/...` | containerd can't reach or auth to Nexus | `docker exec devops-worker curl -s -o /dev/null -w '%{http_code}' http://nexus:8082/v2/` — expect `401`. Not `401`? Re-run [§5.9](phase-0-foundations.md#59-teach-containerd-on-the-kind-nodes-about-nexus). `401` but still failing? The pod is missing `imagePullSecrets` or the ExternalSecret hasn't synced. |
| `curl http://localhost` returns **`000`** | Ingress controller scheduled on a node with no port mappings | `000` = nothing listening, not a 404. `kubectl -n ingress-nginx get pods -o wide` — if `NODE` isn't `devops-control-plane`, apply the `ingress-ready` nodeSelector patch in [§4.3](phase-0-foundations.md#43-install-the-ingress-controller). Upstream dropped that selector in controller-v1.13.0. |
| Ingress Service stuck `EXTERNAL-IP <pending>` | `type: LoadBalancer` with no cloud provider | Harmless on kind — traffic arrives via `hostPort`, not the Service. Don't install MetalLB to "fix" it. |
| Pods can't resolve `nexus` | Nexus container got a new IP | Re-run [§5.10](phase-0-foundations.md#510-teach-pods-about-nexus-coredns) with the current `docker inspect nexus` IP. |
| `docker push` → `http: server gave HTTP response to HTTPS client` | `insecure-registries` not applied | [§5.8](phase-0-foundations.md#58-trust-the-plain-http-registry-from-docker), then **restart Docker**. |
| `docker login nexus:8082` → 401 with correct password | Docker Bearer Token Realm not active | Nexus → ⚙ → Security → Realms → activate it ([§5.4](phase-0-foundations.md#54-create-the-docker-hosted-registry)). |
| CI: `go: ... 401 Unauthorized` from `nexus:8081`, or `uv sync` hangs | Anonymous access disabled in Nexus | Builds pass no credentials to the proxies. Enable global anonymous access ([§5.3](phase-0-foundations.md#53-run-nexus)); Docker pull stays authenticated via the per-repository switch. Check with `curl -o /dev/null -w '%{http_code}' http://nexus:8081/repository/pypi-proxy/simple/` — expect `200`. |
| CI: `uv sync --locked` → "lockfile needs to be updated", but it passes locally | `uv.lock` records a different registry than the build resolves against | Declare the index in `pyproject.toml` via `[[tool.uv.index]]` and re-run `uv lock` ([§3.1](phase-1-the-application.md#31-order-api-python--fastapi)). Setting the index only in CI can never match a committed lock. |
| CI: `go: -race requires cgo` | Test step on an alpine Go image | `golang:1.26-alpine` is `CGO_ENABLED=0` with no gcc. Use `golang:1.26` for the test step ([§12.5](phase-3-delivery.md#125-the-pipeline)). |
| Build fails cloning `buildkite-plugins/kubernetes-buildkite-plugin` | The Buildkite queue is **Hosted**, not Self-hosted | The job ran on Buildkite's machines, which don't understand the `kubernetes` plugin. Queue type can't be changed after creation — delete it and recreate as Self-hosted ([§12.2](phase-3-delivery.md#122-create-the-buildkite-side)). |
| `agent-stack-k8s` logs `job tags do not match expected tags in configuration` | Same as above | A hosted agent adds `namespace-experiments=docker.builder=local`; your controller advertises only `queue=kubernetes`. |
| ClusterSecretStore `Invalid` | OpenBao SA lacks TokenReview, or role name mismatch | `kubectl -n external-secrets logs deploy/external-secrets`. Check the `system:auth-delegator` binding and that the role is `eso` bound to SA `external-secrets` in ns `external-secrets`. |
| ExternalSecret `SecretSyncedError`, `permission denied` | KV v2 path missing the `/data/` segment | The policy must be `path "shop/data/*"`, not `path "shop/*"` ([§7.4](phase-1-the-application.md#74-configure-kubernetes-authentication)). |
| Kafka pods `Pending` | No PVs / insufficient resources | `kubectl -n kafka describe pod <pod>`. On kind the default local-path provisioner needs disk — check Docker's disk allocation. |
| `kubectl wait kafka/orders` times out | Controllers haven't formed a quorum | `kubectl -n kafka logs orders-controller-0`; `kubectl -n kafka describe kafka orders` and read `.status.conditions`. |
| Argo CD `Unknown` / `ComparisonError` | Repo unreachable or chart won't render | `argocd app get order-platform`; `helm template` locally ([§10.3](phase-1-the-application.md#103-render-it-before-you-trust-it)). |
| Argo CD stuck `OutOfSync` after a green build | The deploy commit never landed | Check the Buildkite `bump image tags` step logs; usually a bad or expired GitHub PAT. |
| Buildkite agent never connects | Wrong token, or wrong cluster | `kubectl -n buildkite logs deploy/agent-stack-k8s`. Token must come from the **cluster's** agent tokens page, and the queue must exist. |
| Build step Pending forever | Queue tag mismatch | The step's `agents: { queue: kubernetes }` must equal the controller's `config.tags` value. |
| Buildah `cannot set up namespace` | Not privileged | The `securityContext.privileged: true` in [§12.5](phase-3-delivery.md#125-the-pipeline) is required for this approach. |
| Prometheus target missing | PodMonitor matched nothing | The monitor scrapes `portNumber: 15020`, the sidecar's merged endpoint, so a pod with no sidecar has nothing to scrape. (15020 is unnamed, which is why the monitor uses `portNumber:` and not `port:`; `http-envoy-prom` is 15090 and carries Envoy's own metrics only.) Check `READY 2/2` first, then labels ([§9.6](phase-4-service-mesh.md#96-the-metrics-problem-you-just-created)). |
| Grafana dashboard doesn't appear | ConfigMap label wrong | Must be `grafana_dashboard: "1"` and `sidecar.dashboards.searchNamespace: ALL`. |
| Everything is slow / pods OOMKilled | Docker memory too low | 16 GB minimum with the mesh and portal running ([§1.3](phase-0-foundations.md#13-give-docker-enough-room)). Check with `kubectl top nodes`. |
| Pod stuck `1/2 Running`, app fine | Sidecar can't reach `istiod` | `kubectl -n istio-system logs deploy/istiod`; `istioctl proxy-status` lists proxies and whether they're synced. |
| `RBAC: access denied` on every request | An `AuthorizationPolicy` matched and denied | `istioctl analyze -n shop` first — the usual cause is a `principals` value naming a ServiceAccount that doesn't exist, which denies everything and looks healthy in `kubectl get pods` ([§9.5](phase-4-service-mesh.md#95-authorization-deny-by-default-then-allow-the-paths-that-exist)). |
| `curl` from another namespace → `Connection reset by peer` | STRICT mTLS, and the caller has no sidecar | Working as designed. Enroll the caller's namespace, or confirm you meant to be outside the mesh. |
| A Job never completes, pod sits at `1/2` | Sidecar outlives the job container | Add `sidecar.istio.io/inject: "false"` to the **pod template** ([§9.3](phase-4-service-mesh.md#93-enroll-namespaces--and-decide-deliberately-which-ones)). |
| Kiali graph is empty | No traffic, or `istio_requests_total` missing | Send requests first. Still empty? Query `istio_requests_total` in Prometheus — if it's absent, the PodMonitor isn't scraping the merged endpoint. |
| Backstage template fails at the last step, `action not found` | Scaffolder GitHub module not registered | `backend.add(import('@backstage/plugin-scaffolder-backend-module-github'))` in `packages/backend/src/index.ts`, then rebuild the image ([§14.3](phase-5-developer-portal.md#143-scaffold-the-portal)). |
| Scaffolder PR fails with 403 | Fine-grained PAT missing `Pull requests: RW` | Contents alone is not enough to open a PR. Re-scope the token, update the value in OpenBao, wait for ESO to resync, restart the pod. |
| Scaffolded service builds but never deploys | Chart file missing or malformed | `helm template deploy/charts/order-platform` and look for it. The chart reads `services/*.yaml` — a file that isn't valid YAML renders as nothing, with no error ([§14.6](phase-5-developer-portal.md#146-paved-path-1--a-new-service)). |
| Every page returns `upstream connect error ... reset reason: connection termination` | Ingress backend is in the mesh under STRICT mTLS | Not a dead backend — a refused plaintext connection. NGINX proxies to pod IPs (which name no service for Istio to originate mTLS to) and preserves the browser's `Host:` (which Envoy routes on, and which matches no mesh service). Both annotations are required and are already in the chart: `nginx.ingress.kubernetes.io/service-upstream: "true"` and `nginx.ingress.kubernetes.io/upstream-vhost: "<svc>.<ns>.svc.cluster.local"`. Confirm with the source sidecar's stats — `destination_service_name.PassthroughCluster` means the mesh could not identify the destination. |
| A `200` at the edge, but is mTLS actually on? | Source-side stats report `unknown` even when it is | Read the **destination** reporter: `kubectl -n shop exec deploy/order-api -c istio-proxy -- pilot-agent request GET 'stats?filter=istio_requests_total' \| grep reporter.destination`. Look for `connection_security_policy.mutual_tls` and a real `source_principal`. A `200` alone proves only that bytes moved — plaintext through `PassthroughCluster` returns `200` too. |
| A credential you just wrote to OpenBao is still rejected | ESO polls on `refreshInterval`; the Secret still holds the old value | The `ExternalSecret` reports `Ready=True` the whole time, truthfully — it is synced, to the previous value. Restarting the consumer does not help. Force it: `kubectl -n <ns> annotate externalsecret <name> force-sync="$(date +%s)" --overwrite`, then restart. Diagnose without printing the secret: compare decoded **length** (`... \| base64 -d \| wc -c`) and `bao kv metadata get <path>`'s newest `created_time` against `.status.refreshTime`. |
| Argo reports `Synced` but the live resource is on an old image | Stale cache in the application controller | `kubectl -n argocd annotate app <name> argocd.argoproj.io/refresh=hard --overwrite`. Suspect this when `Synced` and `Degraded` appear together and the rendered manifest in git plainly differs from the live object. |
| `exec /order-worker: no such file or directory` on a file that exists and is executable | The binary is dynamically linked; `distroless/static` has no loader | It is the *loader* that is missing, not the binary. Pants defaults `[golang] cgo_enabled` to true — `pants.toml` sets it to `false` ([§17.2](phase-7-polyglot-monorepo.md)). Check with `readelf -l <binary> \| grep interpreter`: a static binary has no `PT_INTERP`. |
| Every order in the dashboard reads `HTTP 502`, but `curl` against the API returns `202` | The frontend proxies to a port the Service does not publish | Two different paths; only the browser's is broken. `frontend/nginx.conf` must target the **Service** port (`80`), not the container port (`8000`). `checks/` contains a test that fails when the two disagree. |
| Backstage loads a white screen over `http://` | `crypto.randomUUID` is unavailable in an insecure context | Use the `https://` URL. This is a browser restriction, not a Backstage bug. |
| Pods cannot resolve `nexus` after a Docker restart | The Nexus container came back on a different bridge IP | The CoreDNS `hosts` entry pins an IP. Re-run [§5.10](phase-0-foundations.md#510-teach-pods-about-nexus-coredns) with the current `docker inspect nexus` address. |

Generally useful:

```bash
kubectl get events -A --sort-by=.lastTimestamp | tail -30
kubectl describe pod -n <ns> <pod>
kubectl top nodes && kubectl top pods -A --sort-by=memory
argocd app get order-platform --show-operation
```

---

## Appendix C — What this deliberately left out

Everything here is a real gap, listed so you know what you don't have rather than discovering it in production.

| Gap | Why it matters | Where to go next |
|---|---|---|
| **TLS at the edge and to Nexus** | Pod-to-pod is mTLS via Istio ([§9.4](phase-4-service-mesh.md#94-mtls-and-proving-it-is-actually-on)), but the browser→nginx hop, Nexus and OpenBao are still plaintext | cert-manager for issuance, then real certificates on the ingress and on Nexus |
| **Supply-chain security** | No SBOM, no image signing, no vulnerability gate | Syft for SBOMs, Grype/Trivy scanning as a pipeline step, Cosign + Sigstore for signatures, Kyverno to reject unsigned images at admission |
| **Policy enforcement** | Nothing stops a privileged pod being deployed | Kyverno or Gatekeeper; Pod Security Admission at `restricted` on workload namespaces |
| **NetworkPolicies** | Istio authorizes *requests* by identity; nothing yet restricts *packets*. A workload outside the mesh is unconstrained | Default-deny per namespace, then allow-list. Complementary to [§9.5](phase-4-service-mesh.md#95-authorization-deny-by-default-then-allow-the-paths-that-exist), not a substitute for it |
| **Logs and traces** | Metrics only — you can see *that* it broke, not *why* | Loki for logs, Tempo + OpenTelemetry for traces. Grafana already fronts all three |
| **Progressive delivery** | Deploys are all-or-nothing | Argo Rollouts or Flagger for canary/blue-green, gated on the Prometheus metrics you already export |
| **HA and autoscaling** | Fixed replica counts, single Argo CD/OpenBao | HPA on custom metrics (consumer lag), Argo CD HA manifests, OpenBao with Raft + auto-unseal |
| **Real IaC** | The cluster itself is imperative (`kind create`), and the infra paved path emits one-shot Jobs rather than reconciled resources | Terraform/OpenTofu, or Crossplane so [§14.7](phase-5-developer-portal.md#147-paved-path-2--infrastructure) produces an `S3Bucket` custom resource that a controller keeps true |
| **Traces from the mesh** | Envoy can emit spans for every hop and we collect none of them | Tempo + OpenTelemetry; Istio needs only `meshConfig.defaultConfig.tracing` pointed at the collector, and Kiali will then link graph edges to traces |
| **Portal identity** | Backstage runs on guest auth with one shared GitHub token | GitHub OAuth for users, plus a GitHub App so scaffolder PRs are attributed to the person who filled in the form ([§14.8](phase-5-developer-portal.md#148-build-and-deploy-the-portal)) |
| **Least-privilege Nexus role** | We used `nx-admin` for the CI user | Build the scoped privilege list ([§5.5](phase-0-foundations.md#55-create-a-ci-user)) — the quickest real improvement you can make |
| **Dead-letter handling** | Malformed Kafka messages are dropped | A DLQ topic plus an alert on its rate |
| **Multi-environment** | One overlay, `env/local` | Add `env/staging` and `env/prod` with their own Argo Applications; promotion becomes a PR moving a tag between overlays |

---

## Appendix D — Command reference

```bash
# Cluster
kind create cluster --config infra/kind-cluster.yaml
kind delete cluster --name devops
kubectl config use-context kind-devops

# Nexus
docker start nexus
docker exec nexus cat /nexus-data/admin.password
docker login nexus:8082 -u ci

# OpenBao
BAO="kubectl -n openbao exec -i openbao-0 -- env BAO_TOKEN=root BAO_ADDR=http://127.0.0.1:8200 bao"
$BAO kv get shop/order-api
$BAO kv put shop/order-api signing_key=...
$BAO policy read shop-read

# External Secrets
kubectl get clustersecretstore
kubectl -n shop get externalsecret
kubectl -n external-secrets logs deploy/external-secrets -f

# Kafka
kubectl -n kafka get kafka,kafkanodepool,kafkatopic
kubectl -n kafka exec -it orders-broker-0 -- \
  bin/kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
    --describe --group order-worker          # consumer lag

# Argo CD
argocd app list
argocd app get order-platform
argocd app sync order-platform
argocd app history order-platform
argocd app rollback order-platform <id>
argocd app set order-platform --sync-policy none    # incident escape hatch

# Buildkite
kubectl -n buildkite logs deploy/agent-stack-k8s -f
kubectl -n buildkite get pods
BUILDKITE_COMMIT="$(git rev-parse HEAD)" .buildkite/pipeline.sh   # render locally

# Observability
kubectl -n monitoring port-forward svc/monitoring-kube-prometheus-prometheus 9090:9090
kubectl -n shop get podmonitor
kubectl get prometheusrule -A

# Istio
istioctl analyze -n shop                  # config errors kubectl cannot see
istioctl proxy-status                     # every proxy, and whether it is synced
istioctl proxy-config listeners deploy/order-api.shop
kubectl get peerauthentication,authorizationpolicy -A
kubectl get namespace -L istio-injection

# Backstage
kubectl -n backstage logs deploy/backstage -f
helm template deploy/charts/order-platform | grep -c 'kind: Deployment'   # incl. scaffolded

# URLs
# http://shop.localtest.me      order-api
# http://argocd.localtest.me    Argo CD
# http://grafana.localtest.me   Grafana        (admin / admin)
# http://kiali.localtest.me     Kiali          (anonymous)
# http://backstage.localtest.me Backstage      (guest)
# http://localhost:8081         Nexus UI       (admin / admin123)
# nexus:8082                    Docker registry
```

---

## Sources

- [Floci — GitHub](https://github.com/floci-io/floci) · [floci.io](https://floci.io/)
- [kind releases](https://github.com/kubernetes-sigs/kind/releases) · [kind quick start](https://kind.sigs.k8s.io/docs/user/quick-start/)
- [Sonatype Nexus Docker registry docs](https://help.sonatype.com/en/docker-registry.html)
- [OpenBao — Helm chart](https://openbao.org/docs/platform/k8s/helm/run/) · [Kubernetes auth](https://openbao.org/docs/auth/kubernetes/)
- [External Secrets Operator — OpenBao provider](https://external-secrets.io/latest/provider/openbao/) · [Vault provider](https://external-secrets.io/latest/provider/hashicorp-vault/)
- [Strimzi releases](https://github.com/strimzi/strimzi-kafka-operator/releases) · [Strimzi docs](https://strimzi.io/docs/operators/latest/overview)
- [Argo CD getting started](https://argo-cd.readthedocs.io/en/stable/getting_started/) · [releases](https://github.com/argoproj/argo-cd/releases)
- [Buildkite Agent Stack for Kubernetes — installation](https://buildkite.com/docs/agent/self-hosted/agent-stack-k8s/installation) · [PodSpec](https://buildkite.com/docs/agent/self-hosted/agent-stack-k8s/podspec) · [git credentials](https://buildkite.com/docs/agent/self-hosted/agent-stack-k8s/git-credentials)
- [kube-prometheus-stack chart](https://github.com/prometheus-community/helm-charts/tree/main/charts/kube-prometheus-stack)
- [Istio — install with Helm](https://istio.io/latest/docs/setup/install/helm/) · [PeerAuthentication](https://istio.io/latest/docs/reference/config/security/peer_authentication/) · [Prometheus integration](https://istio.io/latest/docs/ops/integrations/prometheus/) · [secure metrics](https://istio.io/latest/docs/tasks/observability/metrics/secure-metrics/)
- [Kiali — installation](https://kiali.io/docs/installation/installation-guide/) · [Prometheus/Grafana configuration](https://kiali.io/docs/configuration/p8s-jaeger-grafana/)
- [Backstage — getting started](https://backstage.io/docs/getting-started/) · [software templates](https://backstage.io/docs/features/software-templates/writing-templates) · [building a Docker image](https://backstage.io/docs/deployment/docker) · [Helm chart](https://github.com/backstage/charts)
- Structural inspiration: [Building a DevOps CI/CD Pipeline Locally](https://medium.com/@deepakkr35/building-a-devops-ci-cd-pipeline-locally-github-jenkins-maven-sonarqube-docker-dockerhub-ba5cf7d58074)

---

[← All phases](README.md) · [← Phase 6 — Operating it, and taking it down](phase-6-operating.md)

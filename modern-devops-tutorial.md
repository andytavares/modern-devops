# Modern DevOps, End to End, On Your Laptop

**Docker · kind (Kubernetes) · Helm · Argo CD · Buildkite · GitHub · OpenBao · Sonatype Nexus · Grafana · Istio · Backstage · Floci · Kafka · Pants · gRPC · Go · Python (FastAPI) · TypeScript**

> Verified against tool versions current as of **2026-08-15**. See [Appendix A](#appendix-a--version-matrix) for the exact pins and how to re-check them.

---

> [!note] This file is assembled from [`docs/`](docs/README.md). Edit the phase files, not this one.
> The phased edition is the source: seven files that each end with something working and checkable —
> cluster → running application → observability → delivery → mesh → portal → operating it. This
> document is those files, end to end, in one page.
>
> It is presented in **build order, not section-number order**. The numbers name the topic and never
> change, so `§7.6` means the same thing here, in `docs/`, and in every wiki citation. The order is
> the sequence you actually type. Those two are not the same: §10.5 tells you the pods come up `1/1`
> with no sidecar, which is only true before §9 turns the mesh on — so §10 is read before §9, and
> sorting this file by number would make it contradict itself.
>
> Read it top to bottom and you end up with the repository this describes. Nothing is skipped, and
> nothing here waits on a section further down.

## 0. What this is, and what it is not


This is a build-it-yourself platform. You will end up with a single-machine environment that has the same *shape* as a real production platform: source in GitHub, CI on Buildkite, artifacts in Nexus, secrets in OpenBao, deploys via Argo CD into Kubernetes, an AWS-shaped dependency emulated by Floci, an event bus on Kafka, and observability in Grafana.

It is not a toy. It is also not production. The difference is stated explicitly every time we take a shortcut, in a **Tradeoff** block. Read those blocks — they are the actual content. Anyone can `helm install`; knowing what you gave up when you did is the job.

**It is shaped like an enterprise, not a startup, and that is a design decision.** Most engineers do not land on a greenfield team that picks its own tools. They land somewhere with an artifact repository they did not choose, a secrets manager another team operates, and a narrow slice of someone else's AWS account — so those things are here, in those roles, with those seams. Where the component a real employer hands you is behind a price tag or an account gate, we substitute the open-source equivalent that teaches the same lesson: **OpenBao** for HashiCorp Vault, **Nexus Repository Community Edition** for Nexus Pro or JFrog Artifactory (from $27,000/year self-managed, as of 2026-08), **Floci** for LocalStack Pro ($39–89 per developer per month; the free tier is non-commercial and requires an account), **Strimzi** for Confluent for Kubernetes or a managed broker like MSK. The substitution is at the *vendor* level, never the *concept* level — each one is chosen because its API, its vocabulary and its failure modes are the ones you will meet at work. Where a substitute stops being equivalent, the section that introduces it says so outright rather than selling you the swap.

**Time:** 6–9 hours if you type everything. **Disk:** ~40 GB. **RAM:** 16 GB free.

### 0.1 The system you're building


```
                    ┌──────────────────────────────────────────────┐
   git push ───────▶│ GitHub: modern-devops (app code + manifests) │
                    └──────────┬──────────────────────┬────────────┘
                               │ webhook              │ polls
                               ▼                      │
                    ┌─────────────────────┐           │
                    │ Buildkite (SaaS     │           │
                    │ control plane)      │           │
                    └──────────┬──────────┘           │
                               │ dispatches jobs      │
   ┌───────────────────────────┼──────────────────────┼─────────────────────────┐
   │  kind cluster "devops"    ▼                      ▼                         │
   │  ┌─────────────────────────────┐   ┌──────────────────────────┐            │
   │  │ buildkite agent-stack-k8s   │   │ Argo CD                  │            │
   │  │  build ▸ test ▸ scan ▸ push │   │  reconciles deploy/ dir  │            │
   │  │  ▸ bump image tag in git    │   └───────────┬──────────────┘            │
   │  └──────────┬──────────────────┘               │ applies                   │
   │             │ push images                      ▼                           │
   │             │                     ┌────────────────────────────┐           │
   │             │                     │ namespace: shop            │           │
   │             │                     │                            │           │
   │             │                     │  order-api (Python/FastAPI)│           │
   │             │                     │      │ 1. PUT payload      │           │
   │             │                     │      │ 2. produce event    │           │
   │             │                     │      ▼                     │           │
   │             │                     │  Kafka (Strimzi, KRaft)    │           │
   │             │                     │      │ topic: orders       │           │
   │             │                     │      ▼                     │           │
   │             │                     │  order-worker (Go)         │           │
   │             │                     │      │ 3. PutItem          │           │
   │             │                     └──────┼─────────────────────┘           │
   │             │                            ▼                                 │
   │             │                     ┌──────────────┐  ┌───────────────────┐  │
   │             │                     │ Floci :4566  │  │ OpenBao + ESO     │  │
   │             │                     │ S3, DynamoDB │  │ secrets ▸ k8s     │  │
   │             │                     └──────────────┘  └───────────────────┘  │
   │             │                                                              │
   │             │   every pod above in shop/ and floci/ carries an Envoy        │
   │             │   sidecar: Istio does mTLS + authz on each hop               │
   │             │                                                              │
   │             │                     ┌──────────────────────────────────────┐ │
   │             │                     │ Prometheus ▸ Grafana ▸ Alertmanager  │ │
   │             │                     │            ▸ Kiali (mesh graph)      │ │
   │             │                     └──────────────────────────────────────┘ │
   │             │                                                              │
   │             │                     ┌──────────────────────────────────────┐ │
   │             │                     │ Backstage: catalog + paved paths     │ │
   │             │                     │   form ▸ PR ▸ CI ▸ Argo CD ▸ running │ │
   │             │                     └──────────────────────────────────────┘ │
   └─────────────┼──────────────────────────────────────────────────────────────┘
                 ▼
        ┌──────────────────────┐
        │ Nexus (Docker host   │  ← container images, PyPI proxy, Go module proxy
        │ container on the     │
        │ "kind" network)      │
        └──────────────────────┘
```

The business flow is deliberately small so the platform is the star:

1. `POST /orders` hits **order-api** (Python/FastAPI).
2. order-api writes the raw order JSON to **S3** (Floci) and produces an event to the **Kafka** topic `orders`.
3. **order-worker** (Go) consumes `orders` and writes a row to **DynamoDB** (Floci).
4. Both services export Prometheus metrics; **Grafana** shows the pipeline end to end, and **Kiali** shows the same traffic as a mesh graph.

Two things sit alongside that flow rather than inside it. **Istio** puts an Envoy sidecar in front of every pod in `shop` and `floci`, so each hop is mutually authenticated and each caller is authorised by cryptographic identity rather than IP. **Backstage** is the front door: a catalog of what exists and two paved paths — new service, new bucket — that turn a form into a reviewed pull request, which CI and Argo CD then carry the rest of the way.

Two languages, because a real platform is polyglot and the interesting problems (image builds, dependency proxying, health checks, metrics conventions) only get interesting when the runtimes differ.

### 0.2 Why these tools


| Slot | Choice | Why this and not the obvious alternative |
|---|---|---|
| Local Kubernetes | **kind** | Runs the real kubelet/containerd in Docker. Multi-node in seconds, config-as-YAML, trivially disposable. Minikube's VM drivers are heavier and its registry story is fiddlier; k3d is excellent but k3s trims components (it swaps in Traefik/servicelb) so you learn a slightly non-standard Kubernetes. |
| CI | **Buildkite** | Hybrid model: the control plane is SaaS, the *agents* run on your infra. That is the actual production pattern for regulated shops — build secrets never leave your network. Jenkins is self-hosted-everything and shows its age; GitHub Actions self-hosted runners blur the trust boundary less cleanly. **Caveat: there is no fully-offline Buildkite.** You need a free buildkite.com org. |
| CD | **Argo CD** | Pull-based GitOps. The cluster converges on git rather than CI pushing into the cluster, so CI never needs cluster credentials. Flux is equally good and more composable; Argo wins here purely on the UI, which makes drift and sync state legible while you're learning. |
| Packaging | **Helm** | Still the lingua franca for third-party software distribution. We use it for our own app too, and [§10.4](#104-tradeoff-helm-vs-kustomize) is honest about when you shouldn't. |
| Artifacts | **Sonatype Nexus** | What you get at work is Nexus Pro or JFrog Artifactory; we run Nexus **Community Edition**, which is the same binary under a usage cap rather than a different product. One box that is a Docker registry *and* a PyPI proxy *and* a Go module proxy, which teaches the real reason artifact repositories exist: not storage, but a supply-chain choke point. [§5.1](#51-what-nexus-is-actually-for) says what CE does not have. |
| Secrets | **OpenBao** | What you get at work is HashiCorp Vault. Vault moved to BUSL in 2023; OpenBao is the Linux Foundation fork of its last MPL version and is API-compatible, so paths, policies, KV v2 and Kubernetes auth transfer verbatim — and the ecosystem already speaks it, which is why External Secrets Operator configures it with its **`vault`** provider. [§7.1](#71-the-problem-with-kubernetes-secrets). |
| Cloud emulation | **Floci** | What you get at work is LocalStack Pro. Its Community edition sunset in March 2026 (auth token required, security updates frozen) and the paid tiers are $39–89 per developer per month. Floci is MIT-licensed, needs no account, and serves the real AWS wire protocol on port 4566 — so what you actually learn is the SDK, not the emulator. [§6.1](#61-why-an-emulator-at-all). |
| Events | **Kafka via Strimzi** | Kafka itself is Apache-2.0 and free; what costs money is *someone running it for you* — MSK, Confluent Cloud, or Confluent for Kubernetes. Strimzi is the CNCF operator that does the same job for free, and it is KRaft-only so you learn the modern topology rather than a ZooKeeper-era one. [§8.1](#81-operator-not-statefulset) says what it does not teach you. |
| Observability | **Grafana** via kube-prometheus-stack | One chart, the whole metrics pipeline: Prometheus Operator, Grafana, Alertmanager, node-exporter, kube-state-metrics. |
| Service mesh | **Istio** (sidecar mode) | The mesh with the deepest documentation and the largest install base, and the one whose vocabulary — `PeerAuthentication`, `AuthorizationPolicy`, SPIFFE identities — you will meet in other people's clusters. Linkerd is genuinely simpler and lighter and is the better choice if mTLS is all you want; we take Istio because [§9.5](#95-authorization-deny-by-default-then-allow-the-paths-that-exist) is the part worth learning and Istio's policy model is the one being copied. |
| Mesh visualisation | **Kiali** | Purpose-built for Istio: it reads the Prometheus you already have plus Istio's config and draws both the traffic graph and the validation errors. Nothing else tells you *"this AuthorizationPolicy references a ServiceAccount that doesn't exist"* without you going looking. |
| Developer portal | **Backstage** | The catalog and scaffolder are the two pieces that matter, and both are open source with no paid tier gating them. Port and Cortex are better products out of the box and worse teachers — the interesting part is defining a paved path, not clicking one. **Caveat: Backstage is a framework you build, not an app you install.** |

---

## 1. Prerequisites


### 1.1 Accounts you actually need


| Service | Cost | Why |
|---|---|---|
| GitHub | Free | Source of truth for both code and manifests. |
| Buildkite | Free tier | SaaS control plane. Sign up at buildkite.com, create an organization. |

Everything else runs on your machine.

### 1.2 Host tooling


Install these first. Versions are floors, not ceilings.

| Tool | Minimum | Check |
|---|---|---|
| Docker Engine / Docker Desktop | 27.x | `docker version` |
| kind | 0.32.0 | `kind version` |
| kubectl | within one minor of your cluster | `kubectl version --client` |
| Helm | **3.8.0** (OCI registry support is mandatory) | `helm version` |
| Go | 1.26.x | `go version` |
| Python | 3.13.x | `python3 --version` |
| uv | 0.12.x | `uv --version` |
| istioctl | 1.30.x | `istioctl version --remote=false` |
| Node.js | Active LTS (22 or 24) | `node --version` |
| Yarn | 4.4.1, via corepack | `yarn --version` |
| git | any recent | `git --version` |
| jq | any recent | `jq --version` |

One shot:

```bash
brew install kind kubectl helm go python@3.13 uv jq istioctl node@22
brew install --cask docker
corepack enable        # provides yarn; §14.3 pins the version
```

> Node and Yarn are only needed for Backstage ([§14](#14-backstage-paved-paths-not-documentation)). `istioctl` is not required to install Istio — we use Helm for that — but `istioctl analyze` and `istioctl proxy-status` are the two commands that turn a silent mesh misconfiguration into a readable error, and you will want them.

### 1.3 Give Docker enough room


The cluster will run Kafka, Prometheus, Argo CD, OpenBao, Floci, Istio, Backstage and your apps simultaneously.

In Docker Desktop: Settings → Resources → set **CPUs ≥ 6**, **Memory ≥ 16 GB**, **Disk ≥ 80 GB**. Apply & Restart.

> **Where the extra memory goes**, since "just give it more RAM" is not an explanation. Istio adds `istiod` (~500 MB) plus an Envoy sidecar of roughly 50–100 MB to *every* pod in an enrolled namespace — with two replicas each of two services, plus Floci and the ingress controller, that is most of a gigabyte. Backstage adds a Node backend and its own PostgreSQL, and its **image build** is the real spike: a `vfs`-backed Buildah pod doing a full `yarn install` will transiently want several gigabytes of disk. If you are capped at 12 GB, the honest advice is to skip the mesh, or run it in ambient mode ([§9.1](#91-what-a-mesh-actually-buys-you-here--and-what-it-doesnt)) where one `ztunnel` per node replaces every sidecar.

> **Tradeoff — one big cluster vs. several small ones.** We run CI, CD, secrets, messaging, observability and workloads in one cluster. Real platforms separate the control plane (Argo CD, CI agents) from workload clusters, so a runaway build can't starve production. We're collapsing that for RAM. Every namespace boundary below is drawn where a *cluster* boundary would be in production — remember which is which.

### 1.4 Verify


```bash
docker run --rm hello-world
kind version && kubectl version --client && helm version --short
```

If `docker run` fails, stop and fix Docker. Nothing downstream works without it.

---

## 2. The repository


One GitHub repo holds both the application code and the deployment manifests.

```
modern-devops/
├── services/                   # one directory with a Dockerfile == one service
│   ├── order-api/            # Python / FastAPI
│   └── order-worker/         # Go
├── portal/                     # Backstage (scaffolded in §14, built by our CI)
├── catalog-info.yaml           # who owns what, and what depends on what
├── deploy/
│   ├── charts/order-platform/  # our Helm chart
│   │   └── services/           # one file per scaffolded service (§14.6)
│   ├── env/local/values.yaml   # the values Argo CD renders (CI writes image tags here)
│   ├── argocd/                 # Argo CD Application manifests (app-of-apps)
│   ├── backstage/templates/    # the paved paths themselves
│   └── platform/               # Strimzi, Floci, OpenBao wiring, ESO stores, Istio
├── .buildkite/
│   ├── pipeline.sh             # generates the pipeline YAML for this commit
│   └── upload.sh               # validates it, then uploads it
└── infra/                      # host-side config: kind cluster, Helm values for
                                #   charts we install by hand (monitoring, Buildkite, Backstage)
```

> **Tradeoff — mono-repo vs. split app/config repos.** Putting manifests next to code means one PR can change both, and there is no cross-repo version skew to reason about. The cost: CI writes a commit back into the same repo it just built from, so you must guard against the deploy commit re-triggering a build (we do, in [§12.5](#125-the-pipeline)). At scale, teams split them — a separate `*-deploy` repo gives config its own review rules, its own access control, and no build/deploy commit loop. For one person on one laptop, mono-repo is strictly simpler. Take the split when more than one team writes to the manifests.

### 2.1 Create it


```bash
mkdir -p ~/Desktop/modern-devops && cd ~/Desktop/modern-devops
git init -b main
mkdir -p services/order-api services/order-worker \
         deploy/charts/order-platform/templates deploy/charts/order-platform/services \
         deploy/env/local \
         deploy/argocd deploy/platform/istio deploy/platform/infra \
         deploy/backstage/templates \
         .buildkite infra
printf '.venv/\n__pycache__/\nbin/\n*.pyc\n.DS_Store\n' > .gitignore
```

Create an **empty** repo on GitHub named `modern-devops` (no README, no license — we want a clean history), then:

```bash
git remote add origin git@github.com:<your-github-user>/modern-devops.git
```

Don't push yet. We'll commit as we go and push at the end of [§3](#3-the-applications).

---

## 4. The Kubernetes cluster


### 4.1 Why the cluster config is not `kind create cluster`


A bare `kind create cluster` gives you one node and a containerd that only trusts Docker Hub. We need three things it doesn't do by default:

1. **Multiple nodes**, so scheduling, anti-affinity and node pressure behave like the real thing.
2. **Ingress-capable ports** on the host, so you can reach Grafana and Argo CD in a browser.
3. **Registry mirroring config**, so containerd will pull from Nexus over plain HTTP.

**`infra/kind-cluster.yaml`**

```yaml
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
name: devops

# Tell containerd on every node to read per-registry configuration from a
# directory. We drop hosts.toml files into it in §4.3. This is the supported
# mechanism (the older `mirrors` config in containerd's TOML is deprecated).
containerdConfigPatches:
  - |-
    [plugins."io.containerd.grpc.v1.cri".registry]
      config_path = "/etc/containerd/certs.d"

nodes:
  - role: control-plane
    kubeadmConfigPatches:
      # Label the node so the ingress controller can target it deterministically.
      - |
        kind: InitConfiguration
        nodeRegistration:
          kubeletExtraArgs:
            node-labels: "ingress-ready=true"
    extraPortMappings:
      - containerPort: 80        # ingress HTTP
        hostPort: 80
        protocol: TCP
      - containerPort: 443       # ingress HTTPS
        hostPort: 443
        protocol: TCP
  - role: worker
  - role: worker
```

> **Tradeoff — `extraPortMappings` vs `kubectl port-forward`.** Port mappings are set at cluster-create time and cannot be changed without recreating the cluster, but they give you stable URLs (`http://argocd.localtest.me`) that behave like a real environment and survive pod restarts. `port-forward` is flexible but dies whenever the pod does, and it teaches you nothing about Ingress. We use port mappings + an Ingress controller for the web UIs, and `port-forward` only for one-off debugging.

> **Node images.** kind ships a default node image matched to its own release; omitting `image:` is the safe choice and is what we do. If you need a specific Kubernetes version, pin it explicitly with the digest published on the [kind release page](https://github.com/kubernetes-sigs/kind/releases) — the tag alone is not sufficient for reproducibility because kind re-publishes node image tags.

### 4.2 Create the cluster


```bash
kind create cluster --config infra/kind-cluster.yaml
```

Expect ~90 seconds. Verify:

```bash
kubectl cluster-info --context kind-devops
kubectl get nodes -o wide
```

You should see three nodes in `Ready` state. If `kubectl` isn't pointed at the new cluster:

```bash
kubectl config use-context kind-devops
```

### 4.3 Install the ingress controller


```bash
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.13.0/deploy/static/provider/kind/deploy.yaml

# REQUIRED. The kind manifest only tolerates the control plane, it doesn't
# require it, so without this patch the controller can land on a worker node,
# bind hostPort 80 there, and be unreachable from your laptop.
kubectl -n ingress-nginx patch deployment ingress-nginx-controller --type=strategic -p \
  '{"spec":{"template":{"spec":{"nodeSelector":{"kubernetes.io/os":"linux","ingress-ready":"true"}}}}}'

kubectl wait --namespace ingress-nginx \
  --for=condition=ready pod \
  --selector=app.kubernetes.io/component=controller \
  --timeout=180s

# Confirm it landed on the node that actually publishes 80/443:
kubectl -n ingress-nginx get pods -o wide
# NODE should be devops-control-plane
```

That manifest is the kind-specific variant: the controller is a **Deployment** whose container
declares `hostPort` 80 and 443. Combined with kind's `extraPortMappings`, that is what puts nginx on
your laptop's port 80 — but **only if the pod is scheduled on the node those mappings belong to**,
which is the control plane. Hence the patch.

The Service will sit at `EXTERNAL-IP <pending>` forever. That is harmless on kind: traffic arrives
via `hostPort`, not through the Service. Don't install MetalLB to "fix" it.

> **`hostPort` is a property of a node, not of a cluster.** Any workload you reach through a fixed
> host port must be pinned to the node that exposes it, and a pod that merely *tolerates* a node is
> not pinned to it.

We'll use `*.localtest.me` hostnames throughout. `localtest.me` and every subdomain of it resolve to `127.0.0.1` from public DNS, so you get real hostname-based routing with zero `/etc/hosts` edits.

Verify:

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://localhost
# 404 is correct — nginx is up and has no matching Ingress yet.
# 000 means nothing is listening on port 80: the controller is on the wrong node.
# Re-check `kubectl -n ingress-nginx get pods -o wide` — NODE must be devops-control-plane.
```

---

## 5. Sonatype Nexus: the artifact choke point


### 5.1 What Nexus is actually for


Most people meet Nexus as "the place images go". That undersells it. An artifact repository is the single point where every dependency entering your build passes through something you control. That gives you:

- **Availability** — your build doesn't break when Docker Hub rate-limits you or PyPI has an outage.
- **Auditability** — you can answer "which builds pulled `left-pad@1.3.0`?"
- **Policy** — you can block a package the moment a CVE lands, without touching a single repo.

We configure three repository types to make that concrete: a **Docker hosted** registry for our images, a **PyPI proxy**, and a **Go proxy**.

> **Why Nexus, and why its free edition rather than Artifactory.** In an enterprise you will be handed Sonatype Nexus Repository Pro or JFrog Artifactory, and the choice between them was made by procurement, not by you. Neither is licensable for a tutorial: JFrog lists self-managed Artifactory from **$27,000/year**, and Nexus Pro is quote-only. So we run `sonatype/nexus3:3.95.0`, which is **Nexus Repository Community Edition** — not a lookalike, the same binary and the same UI as Pro under a usage cap of **40,000 total components or 100,000 requests per day**, after which it refuses new components until you drop below both ([Sonatype](https://help.sonatype.com/en/ce-onboarding.html), as of 2026-08). Everything §5 does — hosted vs proxy vs group, the Docker Bearer Token realm, a separate connector port because the registry API lives at `/v2/`, anonymous access scoped per repository, a private `GOPROXY` — is identical on Pro.
>
> It transfers to Artifactory as well, because the parts that matter are protocols, not products. A Docker registry is the OCI distribution API; a PyPI proxy is PEP 503's simple index; a Go proxy is the module proxy protocol. The client-side configuration in [§5.8](#58-trust-the-plain-http-registry-from-docker)–[§5.10](#510-teach-pods-about-nexus-coredns) — `insecure-registries`, containerd's `hosts.toml`, `PIP_INDEX_URL`, `GOPROXY`, `GOSUMDB=off` — is unchanged against Artifactory, and Artifactory's repository types are Nexus's under other names: **local** = hosted, **remote** = proxy, **virtual** = group.
>
> **Where the free edition genuinely does not teach the same thing.** CE has no high availability, no content replication and no SAML/SSO, so the operational half of running a real artifact repository — multi-site, an outage that is more than downtime, identity federation — is out of scope here and cannot be brought in. Nor is the **Policy** bullet above something you will actually build: blocking a CVE at the choke point is done by Sonatype Repository Firewall / IQ Server or JFrog Xray, both paid. This tutorial teaches you where the choke point is and how everything routes through it. It does not, and cannot, show you what a policy engine bolted onto it feels like in anger.

### 5.2 Networking: the part everyone gets wrong


Nexus needs to be reachable, under **the same name and port**, from three places:

| Caller | Needs to | Reaches Nexus how |
|---|---|---|
| Your laptop shell | `docker push`, browse the UI | published host port |
| containerd on kind nodes | pull images for pods | Docker network DNS (`kind` network) |
| Pods (Buildkite agents running Buildah) | push images, pull PyPI/Go deps | cluster DNS → must be taught |

If the name differs between them, your image reference (`nexus:8082/shop/order-api:abc123`) means different things in different places and you get `ImagePullBackOff` that looks like a permissions bug and isn't.

The fix is three-part, and we do each explicitly:

1. Run Nexus as a Docker container **attached to the `kind` network** with the network alias `nexus`. That covers containerd on the nodes, which resolves via Docker's embedded DNS.
2. Publish ports to the host and add `nexus` to your `/etc/hosts` pointing at `127.0.0.1`. That covers your shell.
3. Add a `hosts` block to CoreDNS mapping `nexus` to the container's IP on the `kind` bridge. That covers pods.

### 5.3 Run Nexus


```bash
docker volume create nexus-data

docker run -d \
  --name nexus \
  --network kind \
  --network-alias nexus \
  --restart unless-stopped \
  -p 8081:8081 \
  -p 8082:8082 \
  -v nexus-data:/nexus-data \
  -e INSTALL4J_ADD_VM_PARAMS="-Xms1200m -Xmx1200m -XX:MaxDirectMemorySize=2g" \
  sonatype/nexus3:3.95.0
```

> The `kind` Docker network is created by `kind create cluster`. If `--network kind` errors with "network not found", your cluster isn't up — go back to [§4.2](#42-create-the-cluster).

Nexus takes 2–4 minutes on first boot (it initialises an embedded database). Watch it:

```bash
docker logs -f nexus 2>&1 | grep -m1 "Started Sonatype Nexus"
```

Get the generated admin password:

```bash
docker exec nexus cat /nexus-data/admin.password && echo
```

Open <http://localhost:8081>, sign in as `admin` with that password. You'll be walked through:

1. **New password** — set something you'll remember. This tutorial assumes `admin123`.
2. **Enable anonymous access?** — choose **Enable anonymous access**. This is required: CI resolves
   dependencies through the PyPI, Go and npm proxies with no credentials at all (`PIP_INDEX_URL` and
   `GOPROXY` are bare URLs), so without it every build fails on `401 Unauthorized`.

> **Anonymous *read on the proxies*, authenticated *everything on the registry*.** This is a narrower
> setting than it sounds. Nexus controls Docker anonymous pulls with a **second, per-repository**
> switch — *"Allow anonymous docker pull"* on the Docker repository itself, which we leave
> **unchecked** in [§5.4](#54-create-the-docker-hosted-registry). Sonatype's docs are explicit:
> *"enabling global anonymous access is necessary, but you also need to enable a repository-level
> setting on each individual Docker repository for anonymous pulls to function correctly"*
> ([anonymous access](https://help.sonatype.com/en/anonymous-access.html)). So global anonymous access
> does **not** give away `docker pull`, and [§7](#7-openbao-and-external-secrets)'s
> OpenBao → ExternalSecret → `imagePullSecret` chain stays exactly as valuable as it was.
>
> Tighten it properly once you're through §5: **⚙ → Security → Roles → `nx-anonymous`** and cut its
> privileges down to `nx-repository-view-pypi-pypi-proxy-*` and `nx-repository-view-go-go-proxy-*`.
> Sonatype recommends precisely this — *"modify the default anonymous role (`nx-anonymous`) to
> restrict access to only necessary content"* ([users](https://help.sonatype.com/en/users.html)).
> Anonymous can then read the language proxies and nothing else.

### 5.4 Create the Docker hosted registry


Nexus separates the *repository* from the *port it is served on*. A Docker repository needs its own HTTP connector because the Docker registry API is served at the root path (`/v2/`) and can't be nested under `/repository/<name>` the way Maven or PyPI can.

In the UI: **⚙ (Settings) → Repository → Repositories → Create repository → `docker (hosted)`**.

| Field | Value |
|---|---|
| Name | `docker-hosted` |
| HTTP | ✅ **checked**, port `8082` |
| Allow anonymous docker pull | ☐ unchecked |
| Docker Registry API — Enable Docker V1 API | ☐ unchecked |
| Blob store | `default` |
| Deployment policy | `Allow redeploy` |

Click **Create repository**.

> **`Allow redeploy` in a tutorial, `Disable redeploy` in production.** Immutable tags are a hard requirement for real GitOps — if `order-api:abc123` can change meaning, then "the git SHA in my manifest" no longer identifies a build, and rollback becomes a lie. We allow redeploy only so you can re-run a failed step without fighting the registry. Every image we push is still tagged with the commit SHA, so nothing depends on mutability.

Now enable the Docker Bearer Token realm, or `docker login` will fail with a confusing 401:

**⚙ → Security → Realms** → move **`docker Bearer Token Realm`** from Available to Active → **Save**.

### 5.5 Create a CI user


Don't use `admin` for automation.

**⚙ → Security → Users → Create local user**:

| Field | Value |
|---|---|
| ID | `ci` |
| First name / Last name | `CI` / `Bot` |
| Email | `ci@localtest.me` |
| Password | `ci-password-change-me` |
| Status | `Active` |
| Roles | `nx-admin` |

> `nx-admin` is lazy and I'm flagging it rather than hiding it. The correct move is a custom role holding only `nx-repository-view-docker-docker-hosted-*` (add/edit/read) plus browse on the proxies. We use `nx-admin` because building the privilege list is 15 clicks of Nexus UI that teach you Nexus's permission model, not DevOps. **If you do one piece of hardening after finishing this tutorial, make it this one.**

### 5.6 Create the PyPI and Go proxies


**Create repository → `pypi (proxy)`**:

| Field | Value |
|---|---|
| Name | `pypi-proxy` |
| Remote storage | `https://pypi.org/` |
| Blob store | `default` |

**Create repository → `go (proxy)`**:

| Field | Value |
|---|---|
| Name | `go-proxy` |
| Remote storage | `https://proxy.golang.org/` |
| Blob store | `default` |

These are reachable at:

- PyPI: `http://nexus:8081/repository/pypi-proxy/simple`
- Go: `http://nexus:8081/repository/go-proxy`

### 5.7 Make `nexus` resolve from your laptop


```bash
echo '127.0.0.1 nexus' | sudo tee -a /etc/hosts
```

Verify:

```bash
curl -s -u ci:ci-password-change-me http://nexus:8082/v2/_catalog
# {"repositories":[]}
```

### 5.8 Trust the plain-HTTP registry from Docker


Docker refuses plain HTTP registries unless you allow them.

In Docker Desktop: Settings → **Docker Engine** → merge into the JSON:

```json
{
  "insecure-registries": ["nexus:8082"]
}
```

**Apply & Restart.**

> **Yes, this is TLS termination by fiat, and no, you would never do it in production.** Plain HTTP means credentials and image layers cross the network in the clear. In production Nexus sits behind TLS with a certificate your nodes trust. We skip it here because issuing and distributing a CA to containerd on three kind nodes is a 20-step detour. The *shape* of what we're configuring — per-registry trust policy on the client — is identical either way.

Confirm Docker can log in:

```bash
docker login nexus:8082 -u ci -p 'ci-password-change-me'
# Login Succeeded
```

### 5.9 Teach containerd (on the kind nodes) about Nexus


`config_path` was set in the cluster config; now we populate it. This must be done on **every** node.

```bash
for node in $(kind get nodes --name devops); do
  docker exec "$node" mkdir -p /etc/containerd/certs.d/nexus:8082
  docker exec -i "$node" tee /etc/containerd/certs.d/nexus:8082/hosts.toml >/dev/null <<'EOF'
server = "http://nexus:8082"

[host."http://nexus:8082"]
  capabilities = ["pull", "resolve"]
EOF
done
```

No containerd restart is needed — `config_path` directories are read per-pull.

Verify a node can resolve and reach Nexus:

```bash
docker exec devops-worker curl -s -o /dev/null -w '%{http_code}\n' http://nexus:8082/v2/
# 401  ← correct: reachable, and demanding auth
```

`401` proves DNS and routing work. A `000` or hang means the container isn't on the `kind` network — check `docker network inspect kind | grep nexus`.

### 5.10 Teach pods about Nexus (CoreDNS)


Pods resolve names through CoreDNS, which knows nothing about Docker networks. Get Nexus's IP on the `kind` bridge and add a static entry.

```bash
NEXUS_IP=$(docker inspect nexus \
  -f '{{ (index .NetworkSettings.Networks "kind").IPAddress }}')
echo "Nexus IP on kind network: $NEXUS_IP"
```

Patch the CoreDNS Corefile. This edits the ConfigMap in place, inserting a `hosts` block:

```bash
kubectl -n kube-system get configmap coredns -o jsonpath='{.data.Corefile}' > /tmp/Corefile.orig

python3 - "$NEXUS_IP" <<'PY'
import subprocess, sys
ip = sys.argv[1]
cm = open('/tmp/Corefile.orig').read()
block = f"""    hosts {{
        {ip} nexus
        fallthrough
    }}
"""
# Insert immediately after the kubernetes plugin block's closing brace.
marker = "    prometheus :9153\n"
assert marker in cm, "unexpected Corefile layout; inspect /tmp/Corefile.orig"
cm = cm.replace(marker, block + marker, 1)
open('/tmp/Corefile.new','w').write(cm)
PY

kubectl -n kube-system create configmap coredns \
  --from-file=Corefile=/tmp/Corefile.new \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl -n kube-system rollout restart deployment coredns
kubectl -n kube-system rollout status deployment coredns --timeout=90s
```

Verify from inside the cluster:

```bash
kubectl run dnstest --rm -it --restart=Never --image=curlimages/curl:8.11.1 -- \
  curl -s -o /dev/null -w '%{http_code}\n' http://nexus:8082/v2/
# 401
```

> **Tradeoff — CoreDNS hosts entry vs. `hostAliases` vs. an in-cluster Nexus.** A CoreDNS entry is cluster-wide and invisible to workload manifests, which is exactly right for infrastructure DNS — but it breaks if the Nexus container is recreated and lands on a different IP (re-run this section if so). `hostAliases` on each pod is per-workload and pollutes every manifest. Running Nexus *inside* the cluster is tempting but makes bootstrap circular: the cluster needs the registry to start workloads, and the registry is a workload. Running the registry outside the cluster it serves is the correct production topology too, for exactly that reason.

### 5.11 Push a first image to prove the whole path


```bash
docker pull alpine:3.21
docker tag alpine:3.21 nexus:8082/smoke/alpine:3.21
docker push nexus:8082/smoke/alpine:3.21

kubectl run smoke --rm -it --restart=Never \
  --image=nexus:8082/smoke/alpine:3.21 \
  --overrides='{"spec":{"imagePullSecrets":[{"name":"nexus-pull"}]}}' \
  -- echo "pulled from nexus"
```

That last command will fail with `ImagePullBackOff` — the `nexus-pull` secret doesn't exist yet. **That failure is the point.** It's the exact symptom you'd hit in production with a misconfigured pull secret, and [§7.6](#76-let-kubernetes-pull-from-nexus) fixes it properly, from OpenBao. Clean up:

```bash
kubectl delete pod smoke --ignore-not-found
```

If you want to confirm the *registry* path independently of auth, create a throwaway secret:

```bash
kubectl create secret docker-registry nexus-pull-tmp \
  --docker-server=nexus:8082 \
  --docker-username=ci \
  --docker-password='ci-password-change-me'

kubectl run smoke --rm -it --restart=Never \
  --image=nexus:8082/smoke/alpine:3.21 \
  --overrides='{"spec":{"imagePullSecrets":[{"name":"nexus-pull-tmp"}]}}' \
  -- echo "pulled from nexus"
# pulled from nexus

kubectl delete secret nexus-pull-tmp
```

That output means containerd resolved `nexus`, authenticated, and pulled a layer. The single hardest part of this tutorial is now behind you.

---

## Where you are

A three-node kind cluster, an ingress controller on the node that actually publishes ports 80 and
443, and Nexus reachable as `nexus` from your shell, from containerd on every node, and from inside
pods. You proved the last one by pushing an image and pulling it back from a node.

Nothing of yours is running yet.

**Next: [Phase 1 — The application, running](#).** You will write two
services, stand up the infrastructure they need, and install them with Helm until an HTTP request
produces a row in a database.

[← All phases](docs/README.md) · [Phase 1 — The application, running →](#)

## 3. The applications


Write the software first. A platform with nothing to deploy teaches you nothing about deploying.

Both services follow the same contract, because *consistency across runtimes is the point of a platform*:

- Config comes from environment variables only. No config files in images.
- `GET /healthz` — liveness. Process is alive.
- `GET /readyz` — readiness. Dependencies are reachable.
- `GET /metrics` — Prometheus text format.
- Logs to stdout, structured JSON.
- Non-root user in the image.

### 3.1 order-api (Python / FastAPI)


Accepts an order, persists the raw payload to S3, publishes an event to Kafka.

**`services/order-api/pyproject.toml`**

```toml
[project]
name = "order-api"
version = "0.1.0"
requires-python = ">=3.13,<3.14"
dependencies = [
    "fastapi[standard]==0.139.2",
    "aiokafka==0.12.0",
    "boto3==1.40.11",
    "prometheus-client==0.23.1",
    "pydantic==2.11.7",
]

[dependency-groups]
dev = [
    "pytest==8.4.1",
    "httpx==0.28.1",
    "ruff==0.12.8",
]

# Declared here, not only as a CI env var, so `uv.lock` records this registry
# and the lock validates identically on a laptop and in the build pod. uv
# refuses a lockfile whose registries aren't in the current index config, so
# setting UV_INDEX_URL in CI alone is not enough.
[[tool.uv.index]]
url = "http://nexus:8081/repository/pypi-proxy/simple"
default = true

[tool.uv]
# Plain HTTP, per §5.8. Without this uv refuses the index outright.
allow-insecure-host = ["nexus"]

[tool.ruff]
line-length = 100

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["order_api"]
```

> **Why the index lives here and not in the CI environment.** It is tempting to leave `pyproject.toml`
> pointing at PyPI and set `UV_DEFAULT_INDEX` (or its deprecated predecessor `UV_INDEX_URL`) only in
> the pipeline. That combination cannot work, and the failure is delayed until CI. `uv.lock` records
> the registry each package came from, and uv refuses a lockfile whose registries aren't in the
> current index configuration — from uv's own resolver:
>
> > *"If the user provided at least one index URL (from the command line, or from a configuration
> > file), don't use the existing lockfile if it references any registries that are no longer included
> > in the current configuration."*
>
> So a lock generated on your laptop against `pypi.org` can never satisfy a build that points uv at
> Nexus, and `uv sync --locked` fails with **"The lockfile at `uv.lock` needs to be updated"** — on a
> lockfile you just committed and which passes locally. Declaring the index in `pyproject.toml` puts
> it *in the lock*, so both environments agree and CI needs no uv-specific environment at all.
>
> Note this pins `nexus:8081` into the project, which is only resolvable in this environment
> ([§5.7](#57-make-nexus-resolve-from-your-laptop)). That is the honest cost of a hermetic index, and
> it is the same trade a real internal PyPI mirror makes.

Create the package directories:

```bash
mkdir -p services/order-api/order_api services/order-api/tests
touch services/order-api/order_api/__init__.py services/order-api/tests/__init__.py
```

The package is `order_api`, not `app`. Name it after the service from the start: a generic top-level
package name collides with every other service's the moment they share a source root.

**`services/order-api/order_api/settings.py`**

```python
import os


class Settings:
    """Config from environment only. Fail loudly at import if something required is missing."""

    def __init__(self) -> None:
        self.kafka_brokers = _req("KAFKA_BROKERS")
        self.kafka_topic = os.getenv("KAFKA_TOPIC", "orders")
        self.s3_bucket = _req("S3_BUCKET")
        self.aws_endpoint_url = os.getenv("AWS_ENDPOINT_URL") or None
        self.aws_region = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
        # Injected by External Secrets Operator from OpenBao. See §7.
        self.signing_key = _req("ORDER_SIGNING_KEY")
        self.service_version = os.getenv("SERVICE_VERSION", "dev")


def _req(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"required environment variable {name} is not set")
    return value


settings = Settings()
```

> **Why fail at import.** A pod that starts successfully and then 500s on every request is much harder to diagnose than one that crash-loops with `required environment variable KAFKA_BROKERS is not set`. Crash-loop is a *good* failure mode: `kubectl get pods` shows it, Argo CD shows it degraded, and the alert fires immediately. Degrading quietly is the bad one.

**`services/order-api/order_api/main.py`**

```python
import hashlib
import hmac
import json
import logging
import sys
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import boto3
from aiokafka import AIOKafkaProducer
from botocore.config import Config as BotoConfig
from fastapi import FastAPI, HTTPException, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from pydantic import BaseModel, Field

from .settings import settings

# ---------- logging ----------
logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format='{"ts":"%(asctime)s","level":"%(levelname)s","msg":"%(message)s"}',
)
log = logging.getLogger("order-api")

# ---------- metrics ----------
ORDERS_RECEIVED = Counter(
    "orders_received_total", "Orders accepted by the API", ["result"]
)
ORDER_LATENCY = Histogram(
    "order_ingest_duration_seconds", "Time to persist and publish one order"
)

# ---------- state ----------
state: dict = {"producer": None, "s3": None, "ready": False}


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Start dependencies before serving; drain them on shutdown."""
    state["s3"] = boto3.client(
        "s3",
        endpoint_url=settings.aws_endpoint_url,
        region_name=settings.aws_region,
        # Floci, like S3-compatible stores generally, needs path-style addressing.
        config=BotoConfig(s3={"addressing_style": "path"}, retries={"max_attempts": 3}),
    )
    producer = AIOKafkaProducer(
        bootstrap_servers=settings.kafka_brokers,
        acks="all",              # do not consider a write done until all ISRs have it
        enable_idempotence=True, # no duplicates on internal retry
        linger_ms=5,
    )
    await producer.start()
    state["producer"] = producer
    state["ready"] = True
    log.info("order-api started version=%s", settings.service_version)
    try:
        yield
    finally:
        state["ready"] = False
        await producer.stop()
        log.info("order-api stopped")


app = FastAPI(title="order-api", version=settings.service_version, lifespan=lifespan)


class OrderIn(BaseModel):
    customer: str = Field(min_length=1, max_length=128)
    sku: str = Field(min_length=1, max_length=64)
    quantity: int = Field(ge=1, le=1000)
    amount_cents: int = Field(ge=1)


@app.get("/healthz")
def healthz() -> dict:
    """Liveness: the process is running. Deliberately checks nothing else."""
    return {"status": "ok", "version": settings.service_version}


@app.get("/readyz")
def readyz() -> dict:
    """Readiness: dependencies are up. Kubernetes pulls us out of the Service if this fails."""
    if not state["ready"]:
        raise HTTPException(status_code=503, detail="dependencies not ready")
    return {"status": "ready"}


@app.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/orders", status_code=202)
async def create_order(order: OrderIn) -> dict:
    started = time.perf_counter()
    order_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()

    payload = order.model_dump() | {"order_id": order_id, "created_at": created_at}
    body = json.dumps(payload, separators=(",", ":")).encode()

    # Sign the payload with a key that only ever exists in OpenBao.
    signature = hmac.new(
        settings.signing_key.encode(), body, hashlib.sha256
    ).hexdigest()

    key = f"orders/{created_at[:10]}/{order_id}.json"
    try:
        state["s3"].put_object(
            Bucket=settings.s3_bucket,
            Key=key,
            Body=body,
            ContentType="application/json",
            Metadata={"signature": signature},
        )
        event = payload | {"s3_key": key, "signature": signature}
        await state["producer"].send_and_wait(
            settings.kafka_topic,
            value=json.dumps(event, separators=(",", ":")).encode(),
            key=order_id.encode(),  # partition by order id → per-order ordering
        )
    except Exception:
        ORDERS_RECEIVED.labels(result="error").inc()
        log.exception("failed to ingest order_id=%s", order_id)
        raise HTTPException(status_code=502, detail="downstream failure")
    finally:
        ORDER_LATENCY.observe(time.perf_counter() - started)

    ORDERS_RECEIVED.labels(result="ok").inc()
    log.info("accepted order_id=%s key=%s", order_id, key)
    return {"order_id": order_id, "status": "accepted", "s3_key": key}
```

Three decisions worth naming:

- **S3 write happens before the Kafka publish.** If the publish fails, we've stored an orphan object — cheap and recoverable. If we published first and the S3 write failed, the worker would consume an event pointing at an object that doesn't exist. Order your side effects so the recoverable failure is the likely one.
- **`acks="all"` + idempotence.** The default is faster and will silently lose writes when a broker restarts. On a 3-broker cluster you want durability; on a benchmark you want speed. Know which one you configured.
- **Partition key = order id.** Kafka only guarantees ordering *within a partition*. Keying by order id means all events for one order land on one partition, so a later "order cancelled" can never overtake "order created".

**`services/order-api/tests/test_api.py`**

```python
import os

# Settings are read at import time, so the environment must be set first.
os.environ.setdefault("KAFKA_BROKERS", "localhost:9092")
os.environ.setdefault("S3_BUCKET", "test-bucket")
os.environ.setdefault("ORDER_SIGNING_KEY", "test-key")

import pytest  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from order_api.main import OrderIn, app, healthz, state  # noqa: E402


def test_healthz_needs_no_dependencies():
    """Liveness must answer without Kafka or S3, or a broker outage kills every pod."""
    assert healthz()["status"] == "ok"


def test_readyz_is_not_ready_before_startup():
    assert state["ready"] is False


@pytest.mark.parametrize(
    "field,value",
    [("quantity", 0), ("quantity", 1001), ("amount_cents", 0), ("customer", "")],
)
def test_invalid_orders_are_rejected(field, value):
    payload = {"customer": "ada", "sku": "W-1", "quantity": 1, "amount_cents": 100}
    payload[field] = value
    with pytest.raises(ValidationError):
        OrderIn(**payload)


def test_valid_order_is_accepted():
    order = OrderIn(customer="ada", sku="W-1", quantity=3, amount_cents=4999)
    assert order.quantity == 3


def test_routes_are_registered():
    paths = {r.path for r in app.routes}
    assert {"/orders", "/healthz", "/readyz", "/metrics"} <= paths
```

> These are deliberately thin. The point of CI tests in this tutorial is to prove the *pipeline* runs them and fails the build when they fail — not to demonstrate test design. Break one on purpose in [§15.4](#154-break-it-on-purpose).

**`services/order-api/Dockerfile`**

```dockerfile
# syntax=docker/dockerfile:1.7
FROM docker.io/library/python:3.13-slim AS builder

# uv resolves and installs an order of magnitude faster than pip, and writes a
# lockfile we can commit for reproducible builds.
COPY --from=ghcr.io/astral-sh/uv:0.12.1 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app
COPY pyproject.toml uv.lock ./
# --no-install-project: dependencies only, so this layer caches across code changes.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project --no-dev

COPY order_api ./order_api
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev


FROM docker.io/library/python:3.13-slim AS runtime
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin appuser
WORKDIR /app
COPY --from=builder --chown=10001:10001 /app /app
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
USER 10001
EXPOSE 8000
CMD ["uvicorn", "order_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

> **Tradeoff — multi-stage build.** The builder stage carries uv and build caches; the runtime stage carries only the virtualenv and your code. Costs you ~15 lines of Dockerfile, saves ~200 MB per image and removes the build toolchain from the attack surface. Always worth it. The `--mount=type=cache` lines require BuildKit, which is the default in Docker 23+ and is supported by Buildah — but note that cache mounts are *builder-local*, so they help your laptop and do nothing for a cold CI pod. Real CI caching means a shared cache backend, which is out of scope here.

Pin the interpreter before anything else, then generate the lockfile the Dockerfile requires:

```bash
cd services/order-api
uv python pin 3.13     # writes .python-version; uv downloads 3.13 if you don't have it
uv lock
uv sync --dev          # creates .venv for local work
uv run pytest -q       # should pass
cd ../..
```

> **`uv python pin` and the `<3.14` bound are not belt-and-braces, they do different jobs — and skipping them produces a spectacular, misleading failure.** Without them, uv picks the newest interpreter on your machine that satisfies `requires-python`. If that is newer than the newest CPython `pydantic-core` publishes wheels for, uv falls back to **building it from source**, and you get a wall of Rust output ending in `the configured Python interpreter version (3.14) is newer than PyO3's maximum supported version (3.13)`. Nothing in that message mentions Python pinning, and the obvious readings — "pydantic is broken", "I need Rust" — are both wrong.
>
> The two mechanisms:
> - **`.python-version`** (written by `uv python pin`) selects the interpreter for *this* project's venv. It is what stops your local environment drifting when Homebrew upgrades `python3` underneath you.
> - **`requires-python = ">=3.13,<3.14"`** is packaging metadata: it constrains *resolution*, so the lockfile can never resolve against an interpreter the container won't run.
>
> The deeper point is dev/prod parity: the Dockerfile above says `FROM python:3.13-slim`. An unpinned local interpreter means you test on one Python and ship on another, and you find out at the worst time. **Pin the interpreter in the same commit that pins the dependencies.**

### 3.2 order-worker (Go)


Consumes `orders`, writes to DynamoDB, exports metrics.

```bash
cd services/order-worker
go mod init github.com/<your-github-user>/modern-devops/services/order-worker
go get github.com/twmb/franz-go/pkg/kgo@latest
go get github.com/aws/aws-sdk-go-v2/config@latest
go get github.com/aws/aws-sdk-go-v2/service/dynamodb@latest
go get github.com/prometheus/client_golang/prometheus@latest
go get github.com/prometheus/client_golang/prometheus/promauto@latest
go get github.com/prometheus/client_golang/prometheus/promhttp@latest
cd ../..
```

> **Why franz-go and not `segmentio/kafka-go` or `confluent-kafka-go`.** franz-go is pure Go (no cgo, so `CGO_ENABLED=0` static builds and scratch images just work), implements the full modern protocol including KRaft-era features, and is actively maintained with a large user base. `confluent-kafka-go` wraps librdkafka — battle-tested but drags cgo into your build. `segmentio/kafka-go` is fine but has thinner coverage of newer protocol features.

**`services/order-worker/main.go`**

```go
// Command order-worker consumes order events from Kafka and persists them to DynamoDB.
package main

import (
	"context"
	"encoding/json"
	"errors"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"strconv"
	"strings"
	"syscall"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	awsconfig "github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	ddbtypes "github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
	"github.com/prometheus/client_golang/prometheus/promhttp"
	"github.com/twmb/franz-go/pkg/kgo"
)

var (
	processed = promauto.NewCounterVec(prometheus.CounterOpts{
		Name: "orders_processed_total",
		Help: "Order events consumed from Kafka and written to DynamoDB.",
	}, []string{"result"})

	processDuration = promauto.NewHistogram(prometheus.HistogramOpts{
		Name:    "order_process_duration_seconds",
		Help:    "Time to persist one order event.",
		Buckets: prometheus.DefBuckets,
	})

	lag = promauto.NewGauge(prometheus.GaugeOpts{
		Name: "order_event_age_seconds",
		Help: "Age of the most recently processed event, from created_at to write time.",
	})
)

type orderEvent struct {
	OrderID     string `json:"order_id"`
	Customer    string `json:"customer"`
	SKU         string `json:"sku"`
	Quantity    int    `json:"quantity"`
	AmountCents int    `json:"amount_cents"`
	CreatedAt   string `json:"created_at"`
	S3Key       string `json:"s3_key"`
	Signature   string `json:"signature"`
}

type config struct {
	brokers []string
	topic   string
	group   string
	table   string
	region  string
	version string
	addr    string
}

func loadConfig() (config, error) {
	c := config{
		topic:   getenv("KAFKA_TOPIC", "orders"),
		group:   getenv("KAFKA_GROUP", "order-worker"),
		region:  getenv("AWS_DEFAULT_REGION", "us-east-1"),
		version: getenv("SERVICE_VERSION", "dev"),
		addr:    getenv("METRICS_ADDR", ":9090"),
	}
	brokers := os.Getenv("KAFKA_BROKERS")
	if brokers == "" {
		return c, errors.New("required environment variable KAFKA_BROKERS is not set")
	}
	c.brokers = strings.Split(brokers, ",")
	c.table = os.Getenv("DDB_TABLE")
	if c.table == "" {
		return c, errors.New("required environment variable DDB_TABLE is not set")
	}
	return c, nil
}

func getenv(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}

func main() {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelInfo}))
	slog.SetDefault(logger)

	cfg, err := loadConfig()
	if err != nil {
		slog.Error("configuration error", "err", err)
		os.Exit(1)
	}

	// SIGTERM is what Kubernetes sends first on pod deletion. Handling it is the
	// difference between a graceful rolling update and dropped in-flight work.
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	// AWS_ENDPOINT_URL is honoured natively by aws-sdk-go-v2, so pointing at Floci
	// needs no code change at all — the same binary runs against real AWS.
	awsCfg, err := awsconfig.LoadDefaultConfig(ctx, awsconfig.WithRegion(cfg.region))
	if err != nil {
		slog.Error("failed to load aws config", "err", err)
		os.Exit(1)
	}
	ddb := dynamodb.NewFromConfig(awsCfg)

	client, err := kgo.NewClient(
		kgo.SeedBrokers(cfg.brokers...),
		kgo.ConsumerGroup(cfg.group),
		kgo.ConsumeTopics(cfg.topic),
		kgo.ConsumeResetOffset(kgo.NewOffset().AtStart()),
		kgo.DisableAutoCommit(), // we commit only after a successful DynamoDB write
		kgo.SessionTimeout(30*time.Second),
	)
	if err != nil {
		slog.Error("failed to create kafka client", "err", err)
		os.Exit(1)
	}
	defer client.Close()

	ready := &atomicBool{}
	go serveHTTP(ctx, cfg, ready)

	if err := client.Ping(ctx); err != nil {
		slog.Error("kafka not reachable", "err", err)
		os.Exit(1)
	}
	ready.set(true)
	slog.Info("order-worker started", "version", cfg.version, "topic", cfg.topic, "table", cfg.table)

	for {
		fetches := client.PollFetches(ctx)
		if ctx.Err() != nil {
			slog.Info("shutting down")
			return
		}
		if errs := fetches.Errors(); len(errs) > 0 {
			for _, e := range errs {
				slog.Error("fetch error", "topic", e.Topic, "partition", e.Partition, "err", e.Err)
			}
			continue
		}

		fetches.EachRecord(func(r *kgo.Record) {
			if err := handle(ctx, ddb, cfg.table, r); err != nil {
				processed.WithLabelValues("error").Inc()
				slog.Error("failed to process record", "offset", r.Offset, "err", err)
				return
			}
			processed.WithLabelValues("ok").Inc()
		})

		// Commit after the batch. At-least-once delivery: a crash between the
		// DynamoDB write and this commit replays the record. PutItem on the same
		// order_id is idempotent, so replay is harmless. That is the trade we
		// chose — see the note below.
		if err := client.CommitUncommittedOffsets(ctx); err != nil {
			slog.Error("commit failed", "err", err)
		}
	}
}

func handle(ctx context.Context, ddb *dynamodb.Client, table string, r *kgo.Record) error {
	start := time.Now()
	defer func() { processDuration.Observe(time.Since(start).Seconds()) }()

	var ev orderEvent
	if err := json.Unmarshal(r.Value, &ev); err != nil {
		// A malformed message will never become valid. Skipping it (rather than
		// retrying forever) keeps the partition moving. In production this record
		// goes to a dead-letter topic instead of the floor.
		slog.Warn("skipping malformed record", "offset", r.Offset, "err", err)
		return nil
	}

	if ts, err := time.Parse(time.RFC3339, ev.CreatedAt); err == nil {
		lag.Set(time.Since(ts).Seconds())
	}

	writeCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()

	_, err := ddb.PutItem(writeCtx, &dynamodb.PutItemInput{
		TableName: aws.String(table),
		Item: map[string]ddbtypes.AttributeValue{
			"order_id":     &ddbtypes.AttributeValueMemberS{Value: ev.OrderID},
			"customer":     &ddbtypes.AttributeValueMemberS{Value: ev.Customer},
			"sku":          &ddbtypes.AttributeValueMemberS{Value: ev.SKU},
			"quantity":     &ddbtypes.AttributeValueMemberN{Value: strconv.Itoa(ev.Quantity)},
			"amount_cents": &ddbtypes.AttributeValueMemberN{Value: strconv.Itoa(ev.AmountCents)},
			"created_at":   &ddbtypes.AttributeValueMemberS{Value: ev.CreatedAt},
			"s3_key":       &ddbtypes.AttributeValueMemberS{Value: ev.S3Key},
			"signature":    &ddbtypes.AttributeValueMemberS{Value: ev.Signature},
		},
	})
	if err != nil {
		return err
	}
	slog.Info("persisted order", "order_id", ev.OrderID, "offset", r.Offset)
	return nil
}

func serveHTTP(ctx context.Context, cfg config, ready *atomicBool) {
	mux := http.NewServeMux()
	mux.Handle("/metrics", promhttp.Handler())
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"status":"ok"}`))
	})
	mux.HandleFunc("/readyz", func(w http.ResponseWriter, _ *http.Request) {
		if !ready.get() {
			w.WriteHeader(http.StatusServiceUnavailable)
			_, _ = w.Write([]byte(`{"status":"not-ready"}`))
			return
		}
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"status":"ready"}`))
	})

	srv := &http.Server{Addr: cfg.addr, Handler: mux, ReadHeaderTimeout: 5 * time.Second}
	go func() {
		<-ctx.Done()
		shutCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		_ = srv.Shutdown(shutCtx)
	}()
	if err := srv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
		slog.Error("metrics server failed", "err", err)
	}
}
```

**`services/order-worker/atomic.go`**

```go
package main

import "sync/atomic"

type atomicBool struct{ v atomic.Bool }

func (a *atomicBool) set(b bool) { a.v.Store(b) }
func (a *atomicBool) get() bool  { return a.v.Load() }
```

**`services/order-worker/main_test.go`**

```go
package main

import (
	"os"
	"testing"
)

func TestLoadConfigRequiresBrokers(t *testing.T) {
	os.Clearenv()
	if _, err := loadConfig(); err == nil {
		t.Fatal("expected an error when KAFKA_BROKERS is unset")
	}
}

func TestLoadConfigDefaults(t *testing.T) {
	os.Clearenv()
	t.Setenv("KAFKA_BROKERS", "a:9092,b:9092")
	t.Setenv("DDB_TABLE", "orders")

	cfg, err := loadConfig()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(cfg.brokers) != 2 {
		t.Fatalf("expected 2 brokers, got %d", len(cfg.brokers))
	}
	if cfg.topic != "orders" {
		t.Fatalf("expected default topic 'orders', got %q", cfg.topic)
	}
	if cfg.group != "order-worker" {
		t.Fatalf("expected default group 'order-worker', got %q", cfg.group)
	}
}
```

> **At-least-once vs exactly-once.** We commit Kafka offsets *after* the DynamoDB write. A crash in between replays the record. Because `PutItem` with the same `order_id` overwrites rather than duplicates, replay is a no-op — the write is idempotent, so at-least-once delivery gives us effectively-once *results*. Exactly-once across Kafka and DynamoDB would need transactional coordination the two systems don't share. **The general lesson: don't buy exactly-once delivery; make your writes idempotent and buy at-least-once, which is cheap.**

**`services/order-worker/Dockerfile`**

```dockerfile
# syntax=docker/dockerfile:1.7
FROM docker.io/library/golang:1.26-alpine AS builder
WORKDIR /src

COPY go.mod go.sum ./
RUN --mount=type=cache,target=/go/pkg/mod go mod download

COPY . .
# CGO_ENABLED=0 → a static binary, which is the only kind that runs on
# distroless/static. -trimpath and -s -w strip build paths and debug info for a
# smaller, more reproducible artifact.
RUN --mount=type=cache,target=/go/pkg/mod \
    --mount=type=cache,target=/root/.cache/go-build \
    CGO_ENABLED=0 GOOS=linux go build \
      -trimpath \
      -ldflags="-s -w" \
      -o /out/order-worker .


FROM gcr.io/distroless/static-debian12:nonroot
# --chmod=0755, not a bare COPY. Once the binary is built outside this Dockerfile
# and shipped in as a CI artifact (Phase 3), the executable bit does not survive
# the transfer, and the pod fails at `exec: "/order-worker": permission denied`
# with no application output at all. Setting it here is correct either way.
COPY --chmod=0755 --from=builder /out/order-worker /order-worker
USER 65532:65532
EXPOSE 9090
ENTRYPOINT ["/order-worker"]
```

> [!warning] **Fully qualify every `FROM`.**
> `docker.io/library/golang:1.26-alpine`, never `golang:1.26-alpine`. Docker assumes Docker Hub for a
> short name; Buildah — which [§12.5](#125-the-pipeline) builds with — runs
> `short-name-mode = "enforcing"` and refuses to guess, so an unqualified name that works on your
> laptop stalls or fails in CI. Pinning the registry is the same discipline as pinning the tag.

> **Tradeoff — distroless vs alpine vs scratch.** Distroless static gives you a non-root user, CA certificates and timezone data, and nothing else — no shell, no package manager, so `kubectl exec` into it is impossible. That's the point: it's a ~2 MB attack surface. The cost is real, though — when something breaks in production you cannot shell in, and you must debug via `kubectl debug --image=busybox` ephemeral containers instead. Alpine keeps a shell at the price of a package manager and musl libc quirks. For a compiled static Go binary, distroless is the right default.

Build and test locally:

```bash
cd services/order-worker
go mod tidy
go vet ./...
go test ./...
cd ../..
```

### 3.3 Commit and push


```bash
git add .
git commit -m "feat: order-api and order-worker services"
git push -u origin main
```

---

## 6. Floci: AWS without AWS


### 6.1 Why an emulator at all


Your app talks to S3 and DynamoDB. You have three options for local development:

| Option | Cost | Fidelity | Verdict |
|---|---|---|---|
| Real AWS | money, credentials on laptops, shared-state collisions | perfect | wrong for a dev inner loop |
| Hand-rolled fakes (in-process mocks) | free | poor — you test your mock, not the SDK | fine for unit tests, useless for integration |
| Emulator (Floci) | free | high — real AWS wire protocol | right |

Floci serves the actual AWS protocol on port 4566, so the AWS SDK, `aws` CLI, IAM signing and pagination all behave normally. Your application code contains **zero** emulator-specific branches — the only difference between local and production is the value of `AWS_ENDPOINT_URL`, which both `boto3` and `aws-sdk-go-v2` honour natively.

> **Why Floci and not LocalStack.** The emulator you will be handed at work is **LocalStack Pro**, and it is the incumbent by a wide margin. We cannot use it here. LocalStack's Community edition sunset in March 2026: basic usage now requires an auth token and the last community release is frozen with no security updates. What replaced it is a free **Hobby** tier that is non-commercial-only and still needs an account, and paid tiers at **$39–89 per developer per month** (as of 2026-08) — a per-seat gate on a tutorial anyone should be able to run offline.
>
> Floci is the open-source stand-in: MIT-licensed, no account, no telemetry, ~69 AWS services, and a drop-in replacement down to serving LocalStack's own `/_localstack/health` endpoint, so existing tooling and Testcontainers wait strategies keep working. Repo: <https://github.com/floci-io/floci>.
>
> **What actually transfers is not Floci.** It is the AWS wire protocol: SigV4-signed requests, `boto3` and `aws-sdk-go-v2` behaviour, pagination, path-style S3 addressing, and the fact that pointing an SDK at an emulator is one environment variable (`AWS_ENDPOINT_URL`) rather than a code branch. Swap Floci for LocalStack Pro on Monday and the only thing that changes is the image name and the auth token. That is the point of choosing an emulator that speaks the real protocol instead of a mock.
>
> **Where it stops being equivalent, stated plainly.** Floci is new — the repo dates from February 2026 — so it has no long track record, and you should expect to meet LocalStack rather than Floci in any real job. LocalStack Pro also emulates things the free tiers of anything do not, notably **IAM policy evaluation**; here, credentials are accepted and never authorised, so nothing in this tutorial teaches you whether your IAM policy is correct. More generally, an emulator is not AWS: IAM semantics, consistency and throttling all differ. It is good enough to build against and not good enough to certify against.

### 6.2 Deploy Floci into the cluster


**`deploy/platform/floci.yaml`**

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: floci
  labels:
    # Mesh enrolment belongs in git, not in a `kubectl label` you run once.
    # Argo CD recreates this Namespace on any teardown, and an imperative
    # label does not come back with it: pods return as 1/1 with no sidecar,
    # STRICT mTLS rejects them and the PodMonitor matches nothing.
    istio-injection: enabled
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: floci
  namespace: floci
  labels: { app.kubernetes.io/name: floci }
spec:
  replicas: 1
  strategy: { type: Recreate }   # single writer; never run two with shared storage
  selector:
    matchLabels: { app.kubernetes.io/name: floci }
  template:
    metadata:
      labels: { app.kubernetes.io/name: floci }
    spec:
      # The `floci` Service is in this namespace, so kubelet would inject
      # FLOCI_PORT=tcp://<clusterIP>:4566. Floci is a Quarkus app and SmallRye
      # Config reads that as the `floci.port` property, which must be an integer.
      # Startup then fails on the injected value. Turn the injection off.
      enableServiceLinks: false
      containers:
        - name: floci
          image: floci/floci:1.5.11
          ports:
            - { name: aws, containerPort: 4566 }
          env:
            # Required when Floci is behind a DNS name other than localhost, so
            # generated endpoints (e.g. S3 virtual-host URLs, SQS queue URLs)
            # point back at something callers can reach.
            - { name: FLOCI_HOSTNAME,           value: "floci.floci.svc.cluster.local" }
            - { name: FLOCI_DEFAULT_REGION,     value: "us-east-1" }
            - { name: FLOCI_DEFAULT_ACCOUNT_ID, value: "000000000000" }
            - { name: FLOCI_STORAGE_MODE,       value: "memory" }
          readinessProbe:
            httpGet: { path: /_localstack/health, port: aws }
            initialDelaySeconds: 2
            periodSeconds: 5
          livenessProbe:
            httpGet: { path: /_localstack/health, port: aws }
            initialDelaySeconds: 10
            periodSeconds: 15
          resources:
            requests: { cpu: 100m, memory: 128Mi }
            limits:   { memory: 1Gi }
---
apiVersion: v1
kind: Service
metadata:
  name: floci
  namespace: floci
spec:
  selector: { app.kubernetes.io/name: floci }
  ports:
    - { name: aws, port: 4566, targetPort: aws }
```

> **`FLOCI_STORAGE_MODE: memory`.** State vanishes on restart, which is correct for a disposable dev environment — every run starts clean and you never debug stale fixtures. Set `persistent` (plus `FLOCI_STORAGE_PERSISTENT_PATH` and a PVC) when you want data to survive; `wal` adds write-ahead logging for crash consistency. Choosing `memory` here also means the bootstrap Job in §6.3 must be re-runnable, which is a property you want anyway.

Apply it:

```bash
kubectl apply -f deploy/platform/floci.yaml
kubectl -n floci rollout status deployment/floci --timeout=120s
```

### 6.3 Bootstrap the S3 bucket and DynamoDB table


Resources have to exist before the app starts. In production this is Terraform or CloudFormation. Here it's a Kubernetes Job, which is the honest local equivalent: declarative, re-runnable, and versioned in git.

**`deploy/platform/floci-bootstrap.yaml`**

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: floci-bootstrap
  namespace: floci
spec:
  backoffLimit: 6
  ttlSecondsAfterFinished: 600
  template:
    metadata:
      annotations:
        # Once §9 enrolls this namespace in the mesh, an injected sidecar would
        # keep this pod alive after the job finishes, so it never completes.
        # Harmless before Istio exists; required after.
        sidecar.istio.io/inject: "false"
    spec:
      restartPolicy: OnFailure
      containers:
        - name: awscli
          image: amazon/aws-cli:2.32.9
          env:
            - { name: AWS_ENDPOINT_URL,      value: "http://floci.floci.svc.cluster.local:4566" }
            - { name: AWS_DEFAULT_REGION,    value: "us-east-1" }
            # Floci does not validate credentials, but the SDK refuses to sign
            # without them, so any non-empty value works.
            - { name: AWS_ACCESS_KEY_ID,     value: "test" }
            - { name: AWS_SECRET_ACCESS_KEY, value: "test" }
          command: ["/bin/sh", "-c"]
          args:
            - |
              set -eu

              echo "waiting for floci..."
              until aws s3 ls >/dev/null 2>&1; do sleep 2; done

              echo "creating bucket orders-raw (idempotent)"
              aws s3api create-bucket --bucket orders-raw 2>/dev/null || true

              echo "creating table orders (idempotent)"
              aws dynamodb create-table \
                --table-name orders \
                --attribute-definitions AttributeName=order_id,AttributeType=S \
                --key-schema AttributeName=order_id,KeyType=HASH \
                --billing-mode PAY_PER_REQUEST 2>/dev/null || true

              aws dynamodb wait table-exists --table-name orders

              echo "--- result ---"
              aws s3 ls
              aws dynamodb list-tables
```

```bash
kubectl apply -f deploy/platform/floci-bootstrap.yaml
kubectl -n floci wait --for=condition=complete job/floci-bootstrap --timeout=180s
kubectl -n floci logs job/floci-bootstrap
```

You should see `orders-raw` and `{"TableNames": ["orders"]}`.

> **Why `|| true` on create.** The Job may be re-run (Floci restarts, `memory` storage, empty state — or Argo CD re-applies it). `create-bucket` on an existing bucket returns an error; swallowing it makes the Job idempotent. The `wait table-exists` afterwards is what actually asserts the desired end state, which is the right way round: **assert the outcome, tolerate the mechanism.**

### 6.4 Reaching Floci from your laptop


Useful for poking at state while debugging:

```bash
kubectl -n floci port-forward svc/floci 4566:4566 &

export AWS_ENDPOINT_URL=http://localhost:4566
export AWS_DEFAULT_REGION=us-east-1
export AWS_ACCESS_KEY_ID=test
export AWS_SECRET_ACCESS_KEY=test

aws s3 ls
aws dynamodb scan --table-name orders
```

Kill the forward with `kill %1` when done.

> **This stops working in [§9.4](#94-mtls-and-proving-it-is-actually-on), and that is the correct behaviour.** `port-forward` delivers plaintext to the pod from outside the mesh, which is exactly what STRICT mTLS exists to refuse — you'll get `Connection reset by peer`, from a command that worked yesterday, with nothing in the application logs. The replacement is to run the client *inside* the mesh instead of tunnelling into it:
>
> ```bash
> kubectl -n floci run awscli --rm -it --restart=Never --image=amazon/aws-cli:2.32.9 \
>   --env AWS_ENDPOINT_URL=http://floci.floci.svc.cluster.local:4566 \
>   --env AWS_DEFAULT_REGION=us-east-1 \
>   --env AWS_ACCESS_KEY_ID=test --env AWS_SECRET_ACCESS_KEY=test \
>   -- s3 ls s3://orders-raw/ --recursive
> ```
>
> That pod gets a sidecar, so it speaks mTLS and satisfies the authorization policy in §9.5 — assuming you added its ServiceAccount, which by default you did not. If it's denied, that's the policy working. Debugging a zero-trust network from outside it is supposed to be hard; the fix is to bring your tools inside, not to poke holes.

---

## 7. OpenBao and External Secrets


### 7.1 The problem with Kubernetes Secrets


A Kubernetes `Secret` is base64-encoded, not encrypted. Anyone with `get secret` in a namespace reads it in plaintext, and if you commit one to git you've published it. That leaves you three bad options and one good one:

| Approach | Problem |
|---|---|
| Secrets in git, plain | Catastrophic. |
| Secrets in git, sealed/encrypted (SOPS, Sealed Secrets) | Works, but rotation means a git commit and a deploy, and revocation is impossible — the old ciphertext is in history forever. |
| Secrets injected by CI | CI now holds every production secret. Your build system becomes the highest-value target in the company. |
| **Secrets in a vault, pulled by the cluster** | Rotation is a vault operation with no deploy. Access is audited per-identity. CI never sees them. |

We take the last one: **OpenBao** stores the secrets, **External Secrets Operator (ESO)** projects them into Kubernetes `Secret` objects that pods consume normally.

> **Why OpenBao rather than HashiCorp Vault.** The secrets manager you will be handed at work is **Vault** — most likely Vault Enterprise, which is quote-only and routinely a five- or six-figure annual contract. Vault also moved to the Business Source License in 2023, so it is no longer open source in any sense a tutorial can rely on. OpenBao is the Linux Foundation fork of the last Mozilla-Public-License version, under open governance, and **API-compatible**.
>
> Be precise about what "transfers" means, because it is more than a hand-wave: paths, ACL policy documents, the KV v2 engine and its `/data/` and `/metadata/` split, the Kubernetes auth method and its TokenReview dependency, tokens and leases, and the `bao`/`vault` CLI verbs are the same on both. So is the ecosystem — which is the concrete proof: ESO configures OpenBao using its **`vault` provider**. There is no separate `openbao` provider key, and expecting one is the single most common mistake here. Everything you type in §7 you can type at a Vault cluster.
>
> **Where it stops being equivalent.** Vault *Community* Edition is free to run, so "we picked OpenBao because Vault costs money" would be a lie — the licence is the gate, not the invoice. The invoice appears one level up, and that is the real gap: Sentinel policy-as-code, performance and disaster-recovery replication, HSM auto-unseal and seal wrapping, and control groups are Vault **Enterprise** features, and this tutorial teaches none of them because neither Vault CE nor OpenBao has them. Namespaces are the partial exception — OpenBao shipped its own, API-compatible with Vault Enterprise's, in 2.3 (beta, May 2025) — but they are not storage- or operator-API-compatible, so a migration is not a copy. Assume the *application-facing* API matches and verify anything operator-facing against OpenBao's own docs rather than Vault's.

### 7.2 Install OpenBao


```bash
helm repo add openbao https://openbao.github.io/openbao-helm
helm repo update

helm upgrade --install openbao openbao/openbao \
  --version 0.29.1 \
  --namespace openbao --create-namespace \
  --set server.dev.enabled=true \
  --set server.dev.devRootToken=root \
  --set injector.enabled=false \
  --wait

kubectl -n openbao get pods
```

You should see `openbao-0` Running.

> **Dev mode is a loaded gun. Here is exactly what you're accepting:** in-memory storage (everything is lost on restart), auto-unsealed at boot (the unseal key is not protected), TLS disabled (tokens cross the network in the clear), and a root token you just typed into your shell history. Production is the opposite of all four: integrated Raft storage on persistent volumes, auto-unseal backed by a KMS/HSM, end-to-end TLS, and no long-lived root token — you generate one with unseal-key quorum, use it, and revoke it. Dev mode exists so you can learn the *data model* without also learning the *operations model* on day one.

> We disable the **agent injector** (`injector.enabled=false`) because we're using ESO instead. The injector is the other valid pattern: a mutating webhook adds a sidecar that writes secrets to a shared volume as files. Sidecar injection gives you live secret rotation without a pod restart and never creates a Kubernetes `Secret` object at all — strictly better isolation. ESO's advantage is that the result is an ordinary `Secret`, so *anything* consumes it (image pull secrets, TLS certs for Ingress, third-party charts that only accept a secret name). We need exactly that in §7.6. Pick the injector when your app can read files and you want zero secrets in etcd; pick ESO when you need interoperability.

### 7.3 Put secrets in OpenBao


Everything below runs the `bao` CLI inside the pod, so nothing is installed on your laptop.

```bash
BAO="kubectl -n openbao exec -i openbao-0 -- env BAO_TOKEN=root BAO_ADDR=http://127.0.0.1:8200 bao"

# KV v2 at the mount point "shop". v2 gives you versioning and soft-delete;
# v1 is a flat overwrite with no history. Always choose v2 for application config.
$BAO secrets enable -path=shop -version=2 kv

# The HMAC key order-api signs payloads with.
$BAO kv put shop/order-api \
  signing_key="$(openssl rand -hex 32)"

# Nexus pull credentials, so Kubernetes can pull our private images.
$BAO kv put shop/nexus \
  username=ci \
  password=ci-password-change-me

# Verify
$BAO kv get shop/order-api
$BAO kv get shop/nexus
```

> **Note the path shape: `shop/<app>`.** Path *is* the authorization boundary in OpenBao — policies are written against path globs. Structuring paths as `<namespace>/<app>` means the policy "order-api may read `shop/order-api/*` and nothing else" is one line. If you flatten everything into `secret/`, every policy becomes an enumeration of individual keys and it rots immediately. **Design your secret paths before you write your first policy.**

### 7.4 Configure Kubernetes authentication


We want pods to authenticate to OpenBao using their Kubernetes ServiceAccount identity — no static token to distribute, rotate, or leak.

The mechanism: a pod presents its projected ServiceAccount JWT; OpenBao calls the Kubernetes `TokenReview` API to verify it; if it matches a configured role, OpenBao issues a short-lived token with the mapped policies.

For OpenBao to call `TokenReview`, its own ServiceAccount needs the `system:auth-delegator` ClusterRole:

```bash
kubectl create clusterrolebinding openbao-token-review \
  --clusterrole=system:auth-delegator \
  --serviceaccount=openbao:openbao
```

Now enable and configure the auth method. This reads the pod's own mounted CA cert and token, so the values are always correct for this cluster:

```bash
kubectl -n openbao exec -i openbao-0 -- sh -c '
set -eu
export BAO_TOKEN=root BAO_ADDR=http://127.0.0.1:8200
SA=/var/run/secrets/kubernetes.io/serviceaccount

bao auth enable kubernetes 2>/dev/null || true

bao write auth/kubernetes/config \
  kubernetes_host="https://${KUBERNETES_SERVICE_HOST}:${KUBERNETES_SERVICE_PORT}" \
  token_reviewer_jwt="$(cat $SA/token)" \
  kubernetes_ca_cert="$(cat $SA/ca.crt)"

echo "kubernetes auth configured"
'
```

Write a policy granting read-only access to the `shop` mount, and a role binding it to the ESO ServiceAccount:

```bash
kubectl -n openbao exec -i openbao-0 -- sh -c '
set -eu
export BAO_TOKEN=root BAO_ADDR=http://127.0.0.1:8200

# KV v2 stores data under <mount>/data/<path>; metadata lives at <mount>/metadata/<path>.
# Forgetting the /data/ segment is the second most common mistake with KV v2.
bao policy write shop-read - <<EOF
path "shop/data/*" {
  capabilities = ["read"]
}
path "shop/metadata/*" {
  capabilities = ["read", "list"]
}
EOF

bao write auth/kubernetes/role/eso \
  bound_service_account_names=external-secrets \
  bound_service_account_namespaces=external-secrets \
  policies=shop-read \
  ttl=1h

echo "policy and role created"
'
```

> **Least privilege, concretely.** The `shop-read` policy grants `read` and nothing else — ESO cannot write, delete, or list secret *values*. The role is bound to one ServiceAccount in one namespace, so a compromised pod in another namespace cannot assume it. `ttl=1h` means a stolen token expires within the hour. Those three constraints — capability, identity binding, lifetime — are the whole of secrets access control. Every vault does it the same way.

### 7.5 Install External Secrets Operator


```bash
helm repo add external-secrets https://charts.external-secrets.io
helm repo update

helm upgrade --install external-secrets external-secrets/external-secrets \
  --version 2.6.0 \
  --namespace external-secrets --create-namespace \
  --set installCRDs=true \
  --wait

kubectl -n external-secrets get pods
```

Three pods: the controller, the webhook, and the cert-controller.

Now create the namespace our app lives in, and a `ClusterSecretStore` pointing at OpenBao:

**`deploy/platform/secret-store.yaml`**

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: shop
  labels:
    # Mesh enrolment belongs in git, not in a `kubectl label` you run once.
    # Argo CD recreates this Namespace on any teardown, and an imperative
    # label does not come back with it: pods return as 1/1 with no sidecar,
    # STRICT mTLS rejects them and the PodMonitor matches nothing.
    istio-injection: enabled
---
apiVersion: external-secrets.io/v1
kind: ClusterSecretStore
metadata:
  name: openbao
spec:
  provider:
    # OpenBao is API-compatible with Vault, so ESO drives it through the
    # `vault` provider. There is no `openbao:` key — this is correct, not a typo.
    vault:
      server: "http://openbao.openbao.svc.cluster.local:8200"
      path: "shop"      # the KV mount point
      version: "v2"
      auth:
        kubernetes:
          mountPath: "kubernetes"
          role: "eso"
          serviceAccountRef:
            name: external-secrets
            namespace: external-secrets
```

```bash
kubectl apply -f deploy/platform/secret-store.yaml
kubectl get clustersecretstore openbao -o jsonpath='{.status.conditions[0]}' && echo
# {"message":"store validated","reason":"Valid","status":"True","type":"Ready"}
```

If it says `Invalid`, check `kubectl -n external-secrets logs deploy/external-secrets` — 99% of the time it's the `system:auth-delegator` binding or a typo in the role name.

> **`ClusterSecretStore` vs `SecretStore`.** A `SecretStore` is namespaced: teams configure their own vault connection and can't reach each other's. A `ClusterSecretStore` is one shared definition — less duplication, but any namespace can reference it, so your isolation now depends entirely on the OpenBao policy rather than on Kubernetes RBAC. We use `ClusterSecretStore` because we have one team; use namespaced stores the moment you have two.

### 7.6 Let Kubernetes pull from Nexus


This is where the ESO choice pays off: we generate a `kubernetes.io/dockerconfigjson` Secret from vault data, using a template.

**`deploy/platform/external-secrets.yaml`**

```yaml
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: nexus-pull
  namespace: shop
spec:
  refreshInterval: "1h"
  secretStoreRef:
    name: openbao
    kind: ClusterSecretStore
  target:
    name: nexus-pull
    creationPolicy: Owner
    template:
      type: kubernetes.io/dockerconfigjson
      data:
        .dockerconfigjson: |
          {
            "auths": {
              "nexus:8082": {
                "username": "{{ .username }}",
                "password": "{{ .password }}",
                "auth": "{{ printf "%s:%s" .username .password | b64enc }}"
              }
            }
          }
  data:
    - secretKey: username
      remoteRef: { key: nexus, property: username }
    - secretKey: password
      remoteRef: { key: nexus, property: password }
---
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: order-api-secrets
  namespace: shop
spec:
  refreshInterval: "1m"
  secretStoreRef:
    name: openbao
    kind: ClusterSecretStore
  target:
    name: order-api-secrets
    creationPolicy: Owner
  data:
    - secretKey: ORDER_SIGNING_KEY
      remoteRef: { key: order-api, property: signing_key }
```

```bash
kubectl apply -f deploy/platform/external-secrets.yaml

kubectl -n shop get externalsecret
# NAME                STORE     REFRESH INTERVAL   STATUS         READY
# nexus-pull          openbao   1h                 SecretSynced   True
# order-api-secrets   openbao   1m                 SecretSynced   True

kubectl -n shop get secret nexus-pull order-api-secrets
```

Prove the round trip:

```bash
kubectl -n shop get secret nexus-pull \
  -o jsonpath='{.data.\.dockerconfigjson}' | base64 -d | jq .
```

Now re-run the smoke test that failed in [§5.11](#511-push-a-first-image-to-prove-the-whole-path):

```bash
kubectl -n shop run smoke --rm -it --restart=Never \
  --image=nexus:8082/smoke/alpine:3.21 \
  --overrides='{"spec":{"imagePullSecrets":[{"name":"nexus-pull"}]}}' \
  -- echo "pulled from nexus using a credential that lives in OpenBao"
```

`creationPolicy: Owner` means ESO owns the Secret and garbage-collects it if the `ExternalSecret` is deleted. That's what you want — otherwise deleting the declaration leaves an orphaned credential in the cluster.

> **`refreshInterval` is a rotation budget, not a preference.** ESO re-reads OpenBao on this interval; if the value changed, it rewrites the Secret. But **an already-running pod does not see the change** — env vars are set at container start and mounted secret volumes update lazily. So the real rotation window is `refreshInterval` + however long until the pod restarts. If you need fast rotation, either mount the secret as a volume and re-read it in-process, or add [Reloader](https://github.com/stakater/Reloader) to restart Deployments when their secrets change. Setting `refreshInterval: 1m` and assuming rotation takes a minute is a mistake people make in production.

Commit:

```bash
git add deploy/ && git commit -m "feat(platform): floci, openbao and external secrets"
```

---

## 8. Kafka with Strimzi


### 8.1 Operator, not StatefulSet


You could write a StatefulSet for Kafka. You'd then own broker ID assignment, rolling restarts that respect in-sync replica counts, certificate rotation, partition rebalancing on scale-up, and KRaft controller quorum management. That is a full-time job.

Strimzi is a Kubernetes **operator**: it turns `Kafka`, `KafkaNodePool` and `KafkaTopic` custom resources into a managed cluster, and encodes the operational knowledge above as controller logic. This is what operators are *for* — stateful software with non-trivial day-2 operations.

> **Modern Kafka is KRaft.** ZooKeeper is gone: Kafka nodes take `controller` and/or `broker` roles and manage metadata via a Raft quorum among the controllers. Strimzi 0.46 and later are KRaft-only (0.45 was the last release supporting ZooKeeper). If you find a tutorial with a `zookeeper:` block in the `Kafka` resource, it is out of date.

### 8.2 Install the operator


```bash
helm repo add strimzi https://strimzi.io/charts/
helm repo update

helm upgrade --install strimzi strimzi/strimzi-kafka-operator \
  --version 0.50.1 \
  --namespace kafka --create-namespace \
  --set watchAnyNamespace=false \
  --wait

kubectl -n kafka get pods
kubectl get crd | grep strimzi
```

`watchAnyNamespace=false` scopes the operator to the `kafka` namespace only. Cluster-wide watching is convenient and is also how one team's malformed CR takes down another team's cluster.

### 8.3 Declare the cluster


Two node pools: a controller quorum and a broker pool. Separating them is the recommended production topology — controllers hold metadata and want stable, small, low-latency nodes; brokers hold data and scale independently.

**`deploy/platform/kafka.yaml`**

```yaml
apiVersion: kafka.strimzi.io/v1beta2
kind: KafkaNodePool
metadata:
  name: controller
  namespace: kafka
  labels:
    strimzi.io/cluster: orders
spec:
  replicas: 3          # Raft quorum: 3 tolerates one failure. Always odd.
  roles:
    - controller
  storage:
    type: jbod
    volumes:
      - id: 0
        type: persistent-claim
        size: 2Gi
        deleteClaim: true
---
apiVersion: kafka.strimzi.io/v1beta2
kind: KafkaNodePool
metadata:
  name: broker
  namespace: kafka
  labels:
    strimzi.io/cluster: orders
spec:
  replicas: 3
  roles:
    - broker
  storage:
    type: jbod
    volumes:
      - id: 0
        type: persistent-claim
        size: 5Gi
        deleteClaim: true
---
apiVersion: kafka.strimzi.io/v1beta2
kind: Kafka
metadata:
  name: orders
  namespace: kafka
  annotations:
    strimzi.io/node-pools: enabled
    strimzi.io/kraft: enabled
spec:
  kafka:
    version: 4.1.0
    metadataVersion: 4.1-IV0
    listeners:
      - name: plain
        port: 9092
        type: internal
        tls: false
    config:
      # With 3 brokers: 3 copies, and a write must reach 2 before it is
      # acknowledged. That survives one broker loss with zero data loss.
      default.replication.factor: 3
      min.insync.replicas: 2
      offsets.topic.replication.factor: 3
      transaction.state.log.replication.factor: 3
      transaction.state.log.min.isr: 2
      auto.create.topics.enable: false
    resources:
      requests: { cpu: 200m, memory: 1Gi }
      limits:   { memory: 2Gi }
  entityOperator:
    topicOperator: {}
    userOperator: {}
---
apiVersion: kafka.strimzi.io/v1beta2
kind: KafkaTopic
metadata:
  name: orders
  namespace: kafka
  labels:
    strimzi.io/cluster: orders
spec:
  partitions: 3
  replicas: 3
  config:
    retention.ms: 604800000     # 7 days
    cleanup.policy: delete
    min.insync.replicas: 2
```

```bash
kubectl apply -f deploy/platform/kafka.yaml

# This takes 3-5 minutes: PVCs bind, controllers form a quorum, then brokers join.
kubectl -n kafka wait kafka/orders --for=condition=Ready --timeout=600s
kubectl -n kafka get pods
kubectl -n kafka get kafkatopic
```

The bootstrap address other namespaces use is:

```
orders-kafka-bootstrap.kafka.svc.cluster.local:9092
```

Four decisions worth naming:

- **`auto.create.topics.enable: false`.** With auto-create on, a typo in a topic name silently produces to a brand-new topic with default settings, and you discover it when a consumer reports zero messages. Off means the typo fails loudly. Declare topics as `KafkaTopic` resources in git — they're config, and config belongs in version control.
- **`min.insync.replicas: 2` with `replicas: 3`.** Producers using `acks=all` (which order-api does) block until 2 replicas have the write. Lose one broker: still writable. Lose two: writes fail rather than silently under-replicating. **Failing writes is the correct behaviour** — the alternative is accepting data you cannot guarantee.
- **3 partitions.** Partition count caps consumer parallelism: 3 partitions means at most 3 useful `order-worker` replicas in one consumer group. You can increase partitions later but never decrease, and increasing changes key→partition mapping, which breaks per-key ordering for in-flight keys. Size it for growth on day one.
- **`deleteClaim: true`.** PVCs are deleted with the cluster. Right for a laptop, catastrophic in production — set `false` there so an accidental `kubectl delete kafka` doesn't take your data with it.

### 8.4 Verify with a real produce/consume


```bash
# Producer (leave this running, type messages, Ctrl-C to exit)
kubectl -n kafka run kafka-producer -ti --rm --restart=Never \
  --image=quay.io/strimzi/kafka:0.50.1-kafka-4.1.0 -- \
  bin/kafka-console-producer.sh \
    --bootstrap-server orders-kafka-bootstrap:9092 \
    --topic orders
```

In a second terminal:

```bash
kubectl -n kafka run kafka-consumer -ti --rm --restart=Never \
  --image=quay.io/strimzi/kafka:0.50.1-kafka-4.1.0 -- \
  bin/kafka-console-consumer.sh \
    --bootstrap-server orders-kafka-bootstrap:9092 \
    --topic orders --from-beginning
```

Type in the producer, see it in the consumer. Ctrl-C both.

```bash
git add deploy/platform/kafka.yaml && git commit -m "feat(platform): kafka via strimzi in kraft mode"
```

---

## 10. Packaging the app with Helm


### 10.1 One chart, two workloads


**`deploy/charts/order-platform/Chart.yaml`**

```yaml
apiVersion: v2
name: order-platform
description: order-api (FastAPI) and order-worker (Go)
type: application
version: 0.1.0
appVersion: "0.1.0"
```

**`deploy/charts/order-platform/values.yaml`**

```yaml
# Defaults. Environment overlays in deploy/env/<env>/values.yaml override these,
# and CI rewrites the image tags there — never here.
global:
  registry: nexus:8082
  imagePullSecret: nexus-pull

kafka:
  brokers: "orders-kafka-bootstrap.kafka.svc.cluster.local:9092"
  topic: "orders"

aws:
  endpointUrl: "http://floci.floci.svc.cluster.local:4566"
  region: "us-east-1"
  s3Bucket: "orders-raw"
  ddbTable: "orders"

orderApi:
  enabled: true
  image:
    repository: shop/order-api
    tag: "dev"
  replicas: 2
  port: 8000
  secretName: order-api-secrets     # produced by the ExternalSecret in §7.6
  resources:
    requests: { cpu: 50m, memory: 128Mi }
    limits:   { memory: 256Mi }
  ingress:
    enabled: true
    className: nginx
    host: shop.localtest.me

orderWorker:
  enabled: true
  image:
    repository: shop/order-worker
    tag: "dev"
  replicas: 2          # <= partition count (3), see §8.3
  metricsPort: 9090
  consumerGroup: order-worker
  resources:
    requests: { cpu: 50m, memory: 64Mi }
    limits:   { memory: 128Mi }

podMonitor:
  # false until §13.2 installs kube-prometheus-stack and with it the
  # monitoring.coreos.com CRDs. Argo CD does not skip a resource whose CRD is
  # missing — it fails the whole sync, so leaving this true strands every
  # workload in `shop` as Missing. Flip to true in §13.3 and commit.
  enabled: false
  interval: 15s

scaffolded:
  tag: "dev"     # CI overwrites this in the env overlay, same as the other two
```

> [!warning] **Leave `podMonitor.enabled: false` until [§13.3](#133-confirm-your-app-is-being-scraped).**
> Argo CD syncs an Application as a unit, so a resource whose CRD is missing fails the *entire* sync —
> with `podMonitor.enabled: true`, `monitoring.coreos.com/v1` does not exist until
> [§13.2](#132-install) and every workload in `shop` stays `Missing`. The flag
> belongs in the **chart's** `values.yaml`, not in `deploy/env/local/values.yaml`, which Buildkite
> rewrites wholesale on every deploy ([§12.5](#125-the-pipeline)).

**`deploy/charts/order-platform/templates/_helpers.tpl`**

```yaml
{{- define "op.labels" -}}
app.kubernetes.io/name: {{ .name }}
app.kubernetes.io/part-of: order-platform
app.kubernetes.io/managed-by: {{ .root.Release.Service }}
app.kubernetes.io/version: {{ .root.Chart.AppVersion | quote }}
{{- end -}}

{{- define "op.image" -}}
{{- printf "%s/%s:%s" .root.Values.global.registry .img.repository .img.tag -}}
{{- end -}}

{{/*
Common env shared by both services. Keeping this in one place is the whole
reason we wrote a chart instead of two YAML files.
*/}}
{{- define "op.commonEnv" -}}
- name: KAFKA_BROKERS
  value: {{ .Values.kafka.brokers | quote }}
- name: KAFKA_TOPIC
  value: {{ .Values.kafka.topic | quote }}
- name: AWS_ENDPOINT_URL
  value: {{ .Values.aws.endpointUrl | quote }}
- name: AWS_DEFAULT_REGION
  value: {{ .Values.aws.region | quote }}
- name: AWS_ACCESS_KEY_ID
  value: "test"
- name: AWS_SECRET_ACCESS_KEY
  value: "test"
{{- end -}}
```

> The static `AWS_ACCESS_KEY_ID: test` is a Floci-ism: the emulator ignores credentials but the AWS SDKs refuse to sign a request without them. In a real cluster these two lines disappear entirely and the pod gets credentials from IRSA / Workload Identity via the ServiceAccount. **That is the one place where "same binary everywhere" leaks** — worth knowing so it doesn't surprise you at promotion time.

**`deploy/charts/order-platform/templates/order-api.yaml`**

```yaml
{{- if .Values.orderApi.enabled }}
apiVersion: v1
kind: ServiceAccount
metadata:
  name: order-api
  labels: {{- include "op.labels" (dict "name" "order-api" "root" $) | nindent 4 }}
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-api
  labels: {{- include "op.labels" (dict "name" "order-api" "root" $) | nindent 4 }}
spec:
  replicas: {{ .Values.orderApi.replicas }}
  selector:
    matchLabels:
      app.kubernetes.io/name: order-api
  strategy:
    type: RollingUpdate
    rollingUpdate: { maxSurge: 1, maxUnavailable: 0 }
  template:
    metadata:
      labels: {{- include "op.labels" (dict "name" "order-api" "root" $) | nindent 8 }}
      annotations:
        # Roll the pods whenever the rendered config changes. Without this,
        # `helm upgrade` with only a value change leaves old pods running.
        checksum/config: {{ toJson .Values | sha256sum }}
        # Istio's agent reads these three, scrapes the app over loopback inside
        # the pod, and re-publishes the result merged with Envoy's own metrics
        # on port 15020. That merged endpoint is what Prometheus scrapes — see
        # §9.6 for why it cannot scrape port 8000 directly any more.
        prometheus.io/scrape: "true"
        prometheus.io/path: "/metrics"
        prometheus.io/port: {{ .Values.orderApi.port | quote }}
    spec:
      # Kubernetes injects a Docker-link env var per Service in this namespace:
      # ORDER_API_PORT, ORDER_WORKER_PORT — each set to "tcp://<clusterIP>:<port>".
      # Any app reading a variable of that name as its own config gets a URL where
      # it expected an integer, and env vars outrank every other config source.
      # Service links are a Docker-links relic nothing here uses.
      enableServiceLinks: false
      serviceAccountName: order-api
      imagePullSecrets:
        - name: {{ .Values.global.imagePullSecret }}
      securityContext:
        runAsNonRoot: true
        seccompProfile: { type: RuntimeDefault }
      containers:
        - name: order-api
          image: {{ include "op.image" (dict "root" $ "img" .Values.orderApi.image) }}
          imagePullPolicy: IfNotPresent
          ports:
            - { name: http, containerPort: {{ .Values.orderApi.port }} }
          env:
            {{- include "op.commonEnv" . | nindent 12 }}
            - name: S3_BUCKET
              value: {{ .Values.aws.s3Bucket | quote }}
            - name: SERVICE_VERSION
              value: {{ .Values.orderApi.image.tag | quote }}
            - name: ORDER_SIGNING_KEY
              valueFrom:
                secretKeyRef:
                  name: {{ .Values.orderApi.secretName }}
                  key: ORDER_SIGNING_KEY
          startupProbe:
            # Gives a slow start up to 60s without loosening the liveness probe,
            # which stays tight so a genuinely wedged pod is killed fast.
            httpGet: { path: /healthz, port: http }
            failureThreshold: 20
            periodSeconds: 3
          livenessProbe:
            httpGet: { path: /healthz, port: http }
            periodSeconds: 10
            failureThreshold: 3
          readinessProbe:
            httpGet: { path: /readyz, port: http }
            periodSeconds: 5
            failureThreshold: 2
          resources: {{- toYaml .Values.orderApi.resources | nindent 12 }}
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities: { drop: ["ALL"] }
---
apiVersion: v1
kind: Service
metadata:
  name: order-api
  labels: {{- include "op.labels" (dict "name" "order-api" "root" $) | nindent 4 }}
spec:
  selector:
    app.kubernetes.io/name: order-api
  ports:
    - { name: http, port: 80, targetPort: http }
{{- if .Values.orderApi.ingress.enabled }}
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: order-api
spec:
  ingressClassName: {{ .Values.orderApi.ingress.className }}
  rules:
    - host: {{ .Values.orderApi.ingress.host }}
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: order-api
                port: { name: http }
{{- end }}
{{- end }}
```

> **`maxUnavailable: 0` + `maxSurge: 1`.** Kubernetes brings up a new pod *before* removing an old one, so capacity never dips during a deploy. It costs one pod's worth of headroom and requires that two versions can run simultaneously — which forces the discipline of backwards-compatible changes. The alternative (`maxUnavailable: 1`) deploys with no extra capacity but drops throughput mid-roll. For anything serving traffic, take the surge.

> **`readOnlyRootFilesystem: true`.** If the app is compromised, the attacker can't drop a binary on disk. It also catches applications that quietly write to `/tmp` — if a pod crashes after you set this, that's a finding, not a reason to turn it off. Add an `emptyDir` volume for legitimate scratch space instead.

**`deploy/charts/order-platform/templates/order-worker.yaml`**

```yaml
{{- if .Values.orderWorker.enabled }}
apiVersion: v1
kind: ServiceAccount
metadata:
  name: order-worker
  labels: {{- include "op.labels" (dict "name" "order-worker" "root" $) | nindent 4 }}
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-worker
  labels: {{- include "op.labels" (dict "name" "order-worker" "root" $) | nindent 4 }}
spec:
  replicas: {{ .Values.orderWorker.replicas }}
  selector:
    matchLabels:
      app.kubernetes.io/name: order-worker
  strategy:
    # A consumer group rebalances on every membership change. Rolling one pod at
    # a time keeps rebalances short; surging would add a member and then remove
    # one, causing two rebalances per pod instead of one.
    type: RollingUpdate
    rollingUpdate: { maxSurge: 0, maxUnavailable: 1 }
  template:
    metadata:
      labels: {{- include "op.labels" (dict "name" "order-worker" "root" $) | nindent 8 }}
      annotations:
        checksum/config: {{ toJson .Values | sha256sum }}
        prometheus.io/scrape: "true"
        prometheus.io/path: "/metrics"
        prometheus.io/port: {{ .Values.orderWorker.metricsPort | quote }}
    spec:
      # Same reason as order-api: no Docker-link env vars in this pod.
      enableServiceLinks: false
      serviceAccountName: order-worker
      imagePullSecrets:
        - name: {{ .Values.global.imagePullSecret }}
      # Give the worker time to finish the in-flight batch and commit offsets
      # after SIGTERM before Kubernetes SIGKILLs it.
      terminationGracePeriodSeconds: 45
      securityContext:
        runAsNonRoot: true
        seccompProfile: { type: RuntimeDefault }
      containers:
        - name: order-worker
          image: {{ include "op.image" (dict "root" $ "img" .Values.orderWorker.image) }}
          imagePullPolicy: IfNotPresent
          ports:
            - { name: metrics, containerPort: {{ .Values.orderWorker.metricsPort }} }
          env:
            {{- include "op.commonEnv" . | nindent 12 }}
            - name: DDB_TABLE
              value: {{ .Values.aws.ddbTable | quote }}
            - name: KAFKA_GROUP
              value: {{ .Values.orderWorker.consumerGroup | quote }}
            - name: SERVICE_VERSION
              value: {{ .Values.orderWorker.image.tag | quote }}
          startupProbe:
            httpGet: { path: /healthz, port: metrics }
            failureThreshold: 30
            periodSeconds: 2
          livenessProbe:
            httpGet: { path: /healthz, port: metrics }
            periodSeconds: 10
            failureThreshold: 3
          readinessProbe:
            httpGet: { path: /readyz, port: metrics }
            periodSeconds: 5
          resources: {{- toYaml .Values.orderWorker.resources | nindent 12 }}
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities: { drop: ["ALL"] }
---
apiVersion: v1
kind: Service
metadata:
  name: order-worker
  labels: {{- include "op.labels" (dict "name" "order-worker" "root" $) | nindent 4 }}
spec:
  selector:
    app.kubernetes.io/name: order-worker
  ports:
    - { name: metrics, port: 9090, targetPort: metrics }
{{- end }}
```

**`deploy/charts/order-platform/templates/podmonitor.yaml`**

```yaml
{{- if .Values.podMonitor.enabled }}
apiVersion: monitoring.coreos.com/v1
kind: PodMonitor
metadata:
  name: order-platform
  labels:
    # kube-prometheus-stack's Prometheus selects monitors by this label in the
    # default configuration we install in §13.
    release: monitoring
spec:
  namespaceSelector:
    matchNames: ["shop"]
  selector:
    matchLabels:
      app.kubernetes.io/part-of: order-platform
  podMetricsEndpoints:
    # istio-proxy's MERGED endpoint on 15020: our application metrics (scraped
    # over loopback inside the pod, per the prometheus.io/* annotations above)
    # plus Envoy's and Istio's. One scrape, all of it, and it survives STRICT.
    #
    # It must be 15020 and it must be addressed by number. Istio: "forwards
    # requests to the sidecar telemetry port 15020 for merged metrics or 15090
    # for Envoy-only metrics". 15090 is the one carrying the port NAME
    # `http-envoy-prom`; 15020 is unnamed in the pod spec, so `port:` cannot
    # reach it and `portNumber:` is required. Selecting http-envoy-prom gets
    # you istio_requests_total (Kiali works) but never the application's own
    # metrics, which is a silent half-failure.
    - portNumber: 15020
      path: /stats/prometheus
      interval: {{ .Values.podMonitor.interval }}
{{- end }}
```

> **Why a PodMonitor and not a ServiceMonitor.** A `ServiceMonitor` selects *Services* and scrapes their endpoints by port name — which is exactly what we did before Istio, with one entry for order-api's `http` port and one for order-worker's `metrics`. Under STRICT mTLS ([§9.6](#96-the-metrics-problem-you-just-created)) both of those scrapes get a connection reset, because Prometheus has no sidecar and no certificate. The merged endpoint lives on the *pod*, on the sidecar's own port, and is not fronted by a Service — so a `PodMonitor` is the only monitor kind that can reach it. `http-envoy-prom` is the port name Istio gives 15090 on every injected pod; `/stats/prometheus` there serves Envoy's metrics with the application's merged in.

> **The trap in this swap:** if a pod has no sidecar, it has no `http-envoy-prom` port, so the PodMonitor silently matches nothing and that workload vanishes from Prometheus with no error. A workload that leaves the mesh loses its metrics. Worth an alert of its own — `absent(up{job="order-platform"})` — which is precisely the kind of "the monitoring stopped" condition [§13.5](#135-an-alert-that-means-something) argues you should page on.

### 10.2 The environment overlay


**`deploy/env/local/values.yaml`**

```yaml
# This file is the deployment contract. Buildkite rewrites the two image tags
# below and commits; Argo CD notices and syncs. Nothing else writes here.
orderApi:
  image:
    tag: "dev"
orderWorker:
  image:
    tag: "dev"
```

### 10.3 Render it before you trust it


`helm template` renders locally without touching the cluster. Do this every time you edit a chart.

```bash
helm template order-platform deploy/charts/order-platform \
  --namespace shop \
  --values deploy/env/local/values.yaml | head -60

# Catch schema errors against the live API without applying:
helm template order-platform deploy/charts/order-platform \
  --namespace shop --values deploy/env/local/values.yaml \
  | kubectl apply --dry-run=server -f -
```

Everything should validate. With `podMonitor.enabled: false` the chart renders nothing that needs a
CRD the cluster doesn't have yet — which is exactly why the flag starts off.

### 10.4 Build the images, by hand, once


Nothing has built your services yet. CI does that from [Phase 3](#) onward; right
now you are the CI.

```bash
SHA="$(git rev-parse --short=12 HEAD)"

for svc in order-api order-worker; do
  docker build -f "services/$svc/Dockerfile" -t "nexus:8082/shop/$svc:$SHA" "services/$svc"
  docker push "nexus:8082/shop/$svc:$SHA"
done

echo "$SHA"
```

> **Use the commit SHA, not `latest`, even by hand.** It costs nothing here and it is the habit the
> whole delivery story depends on later ([§10.3](#103-render-it-before-you-trust-it)). A tag that can
> change meaning turns "what is running?" into a question nobody can answer.

Point the overlay at what you just pushed:

```bash
sed -i.bak "s|tag: \".*\"|tag: \"$SHA\"|g" deploy/env/local/values.yaml && rm deploy/env/local/values.yaml.bak
grep tag: deploy/env/local/values.yaml
```

### 10.5 Install it


```bash
helm upgrade --install order-platform deploy/charts/order-platform \
  --namespace shop --create-namespace \
  --values deploy/env/local/values.yaml \
  --wait --timeout 5m

kubectl -n shop get pods
```

All four pods should reach `Running` and `1/1`. Not `2/2` — there is no sidecar yet; that is
[Phase 4](#).

**Now the whole point of the phase:**

```bash
for i in $(seq 1 20); do
  curl -sS -o /dev/null -w '%{http_code} ' -X POST http://shop.localtest.me/orders \
    -H 'content-type: application/json' \
    -d '{"customer":"ada","sku":"WIDGET-1","quantity":1,"amount_cents":1999}'
done; echo
```

Twenty `202`s. Then confirm the data actually landed at both ends — the API's write to S3, and the
worker's write to DynamoDB after it consumed the Kafka event:

```bash
kubectl -n floci run awscli --rm -i --restart=Never --image=amazon/aws-cli:2.32.9 \
  --env AWS_ENDPOINT_URL=http://floci.floci.svc.cluster.local:4566 \
  --env AWS_ACCESS_KEY_ID=test --env AWS_SECRET_ACCESS_KEY=test \
  --env AWS_DEFAULT_REGION=us-east-1 -- \
  s3 ls s3://orders-raw/orders/ --recursive | tail -3

kubectl -n floci run awscli --rm -i --restart=Never --image=amazon/aws-cli:2.32.9 \
  --env AWS_ENDPOINT_URL=http://floci.floci.svc.cluster.local:4566 \
  --env AWS_ACCESS_KEY_ID=test --env AWS_SECRET_ACCESS_KEY=test \
  --env AWS_DEFAULT_REGION=us-east-1 -- \
  dynamodb scan --table-name orders --select COUNT
```

`Count` should equal the number of orders you posted. If S3 has objects and DynamoDB has none, the
API is fine and the worker is not — start with `kubectl -n shop logs deploy/order-worker`.

> **What you just did, and why Phase 3 exists.** You built an image, remembered its tag, edited a
> file, and ran `helm upgrade` from a laptop that happens to have cluster credentials. It works.
> Now notice: nothing recorded any of it, the only record of *what is deployed* is the cluster
> itself, and the deploy required you to be awake. Hold onto that feeling — it is the entire argument
> for [Phase 3](#), and it is much more convincing now than it would have been as
> an assertion three phases ago.

### 10.6 Tradeoff: Helm vs Kustomize


| | Helm | Kustomize |
|---|---|---|
| Mechanism | Go templates → YAML | Strategic merge patches on real YAML |
| Best at | distributing software to strangers; conditional/parameterised output | overlaying environments onto manifests you own |
| Failure mode | template logic becomes a program nobody can read; `{{- if }}` nesting three deep | patch files multiply; hard to see the final object without rendering |
| Versioned artifact | yes, charts are packaged and pushed to a registry | no native packaging |
| Rollback | `helm rollback` (release history in-cluster) | whatever git says |

We use Helm because we need one thing Kustomize genuinely can't do cleanly: **a single parameter that CI can mechanically rewrite**, with the rest of the manifest derived from it. Kustomize's `images:` transformer does exactly this too, and if your only variance across environments is image tags and replica counts, Kustomize is the simpler, more auditable choice — you can read the output without rendering anything.

The rule of thumb: **Helm for software you ship to others, Kustomize for software you run yourself.** We're technically on the wrong side of that rule and doing it anyway, because you will spend your career reading other people's charts and it's worth building the muscle. Note that Argo CD supports both natively — this is not a lock-in decision.

```bash
git add deploy/ && git commit -m "feat(deploy): helm chart for order-platform"
```

---

## Where you are

`curl -X POST http://shop.localtest.me/orders` returns `202`. The payload is signed with a key that
only ever existed in OpenBao, written to S3, published to Kafka, consumed by `order-worker` and
written to DynamoDB. That is a real distributed system, on a laptop, with no cloud account.

It is also entirely undefended and entirely unobserved:

- You cannot tell whether it is healthy without `kubectl logs`.
- Deploying means you, typing, remembering an image tag.
- Any pod in the cluster can call `floci` directly.

**Next: [Phase 2 — Seeing what it does](#)**, because the first of those is
the one that makes the other two safe to fix.

[← All phases](docs/README.md) · [← Phase 0 — Foundations](#) · [Phase 2 — Seeing what it does →](#)

## 13. Observability with Grafana


### 13.1 What to install and why it's one chart


`kube-prometheus-stack` bundles the Prometheus Operator, Prometheus, Alertmanager, Grafana, node-exporter and kube-state-metrics, pre-wired with dashboards and recording rules for Kubernetes itself. Assembling those by hand is a week of work to arrive at a worse version of the same thing.

The Operator is the important part: it introduces `ServiceMonitor`, `PodMonitor` and `PrometheusRule` CRDs, so **applications declare their own scrape config and alerts** in their own charts. No central `prometheus.yml` that every team has to send a PR against. Our chart already ships a `ServiceMonitor` ([§10.1](#101-one-chart-two-workloads)) — this is what makes it work.

### 13.2 Install


```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update
helm search repo prometheus-community/kube-prometheus-stack --versions | head -3
```

Pin whatever the top line reports; `88.3.0` is known-good and is the version used below.

**`infra/monitoring-values.yaml`**

```yaml
grafana:
  adminPassword: admin
  ingress:
    enabled: true
    ingressClassName: nginx
    hosts: ["grafana.localtest.me"]
  defaultDashboardsTimezone: browser
  sidecar:
    dashboards:
      enabled: true
      # Any ConfigMap in any namespace with this label becomes a dashboard.
      # That is how app teams ship dashboards with their app, not via a ticket.
      label: grafana_dashboard
      searchNamespace: ALL

prometheus:
  prometheusSpec:
    retention: 24h
    # Empty selectors = "discover ServiceMonitors regardless of Helm labels".
    # The chart's default restricts discovery to objects carrying its own release
    # label, which silently drops third-party monitors and causes hours of
    # "why is my target missing" debugging.
    serviceMonitorSelectorNilUsesHelmValues: false
    podMonitorSelectorNilUsesHelmValues: false
    ruleSelectorNilUsesHelmValues: false
    resources:
      requests: { cpu: 200m, memory: 512Mi }
      limits:   { memory: 1500Mi }

alertmanager:
  alertmanagerSpec:
    resources:
      requests: { cpu: 50m, memory: 128Mi }
      limits:   { memory: 256Mi }

# Two components that do not work on kind: kubelet's control-plane endpoints
# are not individually addressable the way a managed cluster exposes them.
kubeControllerManager: { enabled: false }
kubeScheduler: { enabled: false }
kubeEtcd: { enabled: false }
kubeProxy: { enabled: false }
```

```bash
helm upgrade --install monitoring prometheus-community/kube-prometheus-stack \
  --version 88.3.0 \
  --namespace monitoring --create-namespace \
  --values infra/monitoring-values.yaml \
  --wait --timeout 15m

kubectl -n monitoring get pods
```

> **`serviceMonitorSelectorNilUsesHelmValues: false` is the single most useful line in that file.** With the default (`true`), Prometheus only picks up ServiceMonitors labelled `release: monitoring`. Our chart sets that label deliberately — but any chart that doesn't will be silently ignored, with no error anywhere. Turning the restriction off trades a little namespace hygiene for monitors that get discovered whoever shipped them.

Grafana is now at <http://grafana.localtest.me> (`admin` / `admin`).

### 13.3 Confirm your app is being scraped


The CRDs exist now, so turn the monitor on. **Which one depends on where you are in the build**, and
right now there is no service mesh, so Prometheus can talk to your pods directly:

```yaml
# In deploy/charts/order-platform/values.yaml — NOT the env/local overlay,
# which Buildkite rewrites once you reach Phase 3.
serviceMonitor:
  enabled: true
  interval: 15s
```

```bash
helm upgrade --install order-platform deploy/charts/order-platform \
  --namespace shop --values deploy/env/local/values.yaml --wait

kubectl -n shop get servicemonitor
```

> **Two monitors ship in this chart and exactly one should ever be on.** `serviceMonitor` selects
> Services and scrapes their metrics port over plaintext — the obvious approach, and correct until
> [Phase 4](#) turns on STRICT mTLS and Prometheus loses the ability to speak
> plaintext to anything. `podMonitor` is the replacement for that world, and
> [§9.6](#96-the-metrics-problem-you-just-created) is where you switch. Turning
> both on double-scrapes every target and doubles your counters.

Port-forward Prometheus and check targets:

```bash
kubectl -n monitoring port-forward svc/monitoring-kube-prometheus-prometheus 9090:9090 &
open http://localhost:9090/targets   # or just browse there
```

Look for `serviceMonitor/shop/order-platform/0`, with one target per pod, all `UP`. If targets are
missing, the usual causes in order of likelihood: the `release: monitoring` label is absent from the
monitor (see the selector note in [§13.2](#132-install)), the `namespaceSelector` is wrong, or the
selector labels don't match the **Service** labels.

Confirm your own metrics are arriving:

```bash
curl -s 'http://localhost:9090/api/v1/query?query=orders_received_total' | jq '.data.result | length'
```

Non-zero once traffic has flowed. Generate some if you haven't:

```bash
for i in $(seq 1 50); do
  curl -sS -o /dev/null -X POST http://shop.localtest.me/orders \
    -H 'content-type: application/json' \
    -d '{"customer":"ada","sku":"WIDGET-1","quantity":1,"amount_cents":100}'
done
```

> **`istio_requests_total` is empty and that is correct.** There is no Istio yet. You get your own
> application metrics and nothing else — which is worth seeing, because it makes concrete how much of
> a mesh's observability value comes from the mesh rather than from Prometheus.

### 13.4 A dashboard, as code


Dashboards clicked together in the UI are lost when the pod restarts. Ship them as ConfigMaps.

**`deploy/platform/grafana-dashboard.yaml`**

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: order-platform-dashboard
  namespace: monitoring
  labels:
    grafana_dashboard: "1"     # the sidecar's selector from §13.2
data:
  order-platform.json: |
    {
      "title": "Order Platform",
      "uid": "order-platform",
      "timezone": "browser",
      "refresh": "10s",
      "time": { "from": "now-30m", "to": "now" },
      "panels": [
        {
          "type": "timeseries",
          "title": "Orders accepted / sec (API)",
          "gridPos": { "h": 8, "w": 12, "x": 0, "y": 0 },
          "targets": [
            {
              "expr": "sum by (result) (rate(orders_received_total[1m]))",
              "legendFormat": "{{result}}"
            }
          ]
        },
        {
          "type": "timeseries",
          "title": "Orders persisted / sec (Worker)",
          "gridPos": { "h": 8, "w": 12, "x": 12, "y": 0 },
          "targets": [
            {
              "expr": "sum by (result) (rate(orders_processed_total[1m]))",
              "legendFormat": "{{result}}"
            }
          ]
        },
        {
          "type": "timeseries",
          "title": "Ingest latency p50 / p95 / p99",
          "gridPos": { "h": 8, "w": 12, "x": 0, "y": 8 },
          "targets": [
            { "expr": "histogram_quantile(0.50, sum by (le) (rate(order_ingest_duration_seconds_bucket[5m])))", "legendFormat": "p50" },
            { "expr": "histogram_quantile(0.95, sum by (le) (rate(order_ingest_duration_seconds_bucket[5m])))", "legendFormat": "p95" },
            { "expr": "histogram_quantile(0.99, sum by (le) (rate(order_ingest_duration_seconds_bucket[5m])))", "legendFormat": "p99" }
          ]
        },
        {
          "type": "stat",
          "title": "Pipeline lag (event age, seconds)",
          "gridPos": { "h": 8, "w": 6, "x": 12, "y": 8 },
          "targets": [ { "expr": "max(order_event_age_seconds)" } ]
        },
        {
          "type": "stat",
          "title": "Unprocessed (accepted - persisted)",
          "gridPos": { "h": 8, "w": 6, "x": 18, "y": 8 },
          "targets": [
            { "expr": "sum(orders_received_total{result=\"ok\"}) - sum(orders_processed_total{result=\"ok\"})" }
          ]
        }
      ]
    }
```

```bash
kubectl apply -f deploy/platform/grafana-dashboard.yaml
```

Within ~30 seconds the sidecar imports it. Find it in Grafana under **Dashboards → Order Platform**.

> **Percentiles come from histograms, not from averages.** `rate(x_sum[5m]) / rate(x_count[5m])` gives you a mean, and the mean latency of a system with a bimodal distribution is a number that describes no request that ever happened. `histogram_quantile` over `_bucket` is the correct instrument. The catch: bucket boundaries are fixed at instrumentation time, so a p99 that lands in your top bucket reads as the bucket's upper bound. Check `prometheus.DefBuckets` covers your real latency range.

### 13.5 An alert that means something


**`deploy/platform/alerts.yaml`**

```yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: order-platform
  namespace: monitoring
  labels:
    release: monitoring
spec:
  groups:
    - name: order-platform
      interval: 30s
      rules:
        - alert: OrderPipelineStalled
          # Orders coming in, none going out, for 5 minutes.
          expr: |
            sum(rate(orders_received_total{result="ok"}[5m])) > 0
            and
            sum(rate(orders_processed_total{result="ok"}[5m])) == 0
          for: 5m
          labels: { severity: critical }
          annotations:
            summary: "Orders are being accepted but nothing is being persisted"
            description: "order-worker is not consuming. Check consumer group lag and worker logs."

        - alert: OrderIngestErrorRate
          expr: |
            sum(rate(orders_received_total{result="error"}[5m]))
            /
            sum(rate(orders_received_total[5m])) > 0.05
          for: 10m
          labels: { severity: warning }
          annotations:
            summary: "order-api error rate above 5%"

        - alert: OrderEventAgeHigh
          expr: max(order_event_age_seconds) > 120
          for: 5m
          labels: { severity: warning }
          annotations:
            summary: "Order events are more than 2 minutes old"
```

```bash
kubectl apply -f deploy/platform/alerts.yaml
```

Check they loaded at <http://localhost:9090/rules>.

> **Alert on symptoms, not causes.** `OrderPipelineStalled` fires when the business outcome fails — orders in, nothing out — regardless of *why* (worker crashed, Kafka unreachable, DynamoDB rejecting, consumer group stuck). One alert covers a dozen root causes. Alerts like "worker pod restarted" fire constantly during normal deploys and train people to ignore the pager. **Every alert should be something a human must act on right now**; if it isn't, it's a dashboard panel.

> **The `for:` clause is not padding.** `for: 5m` means the condition must hold continuously. Without it, a 20-second blip during a rolling deploy pages someone at 3am. Too long, and you find out late. Tune it against your actual deploy duration.

```bash
git add deploy/platform infra/monitoring-values.yaml
git commit -m "feat(observability): prometheus, grafana dashboard and alerts"
git push
```

### 13.6 Kiali: the mesh you can see


Everything in [§9](#9-istio-the-service-mesh) is invisible. mTLS either works or it doesn't; an `AuthorizationPolicy` either matches or it doesn't; and when it doesn't, the symptom is a 403 in a log somewhere. Kiali reads the same Prometheus you just installed plus Istio's configuration, and draws the answer.

It is documented here, next to Prometheus, because **without Prometheus there is no graph**: Kiali's
topology is derived entirely from `istio_requests_total`, and it reads that metric out of the
Prometheus you just installed.

**Run this section after [Phase 4](#), not now.** Kiali installs into
`istio-system` and needs that namespace, the mesh, and the merged-metrics scrape from
[§9.6](#96-the-metrics-problem-you-just-created) to exist first. Come back to
it when [§9.6](#96-the-metrics-problem-you-just-created) is done.

```bash
helm repo add kiali https://kiali.org/helm-charts
helm repo update

helm upgrade --install kiali-server kiali/kiali-server \
  --namespace istio-system --version 2.30.0 \
  --set auth.strategy=anonymous \
  --set external_services.prometheus.url=http://monitoring-kube-prometheus-prometheus.monitoring:9090 \
  --set external_services.grafana.enabled=true \
  --set external_services.grafana.internal_url=http://monitoring-grafana.monitoring \
  --set external_services.grafana.external_url=http://grafana.localtest.me \
  --wait
```

> **`auth.strategy=anonymous` means anyone who can reach the URL is an admin.** Kiali can *change* Istio configuration from the UI, so on a real cluster this is a privilege-escalation path with a web interface. It is acceptable here because the only route to it is `localhost` on your laptop. The production settings are `openid` or `header`; the default is `token`, which makes you paste a ServiceAccount token at every login and is the right friction outside a lab.

Give it an Ingress, consistent with everything else:

**`deploy/platform/kiali-ingress.yaml`**

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: kiali
  namespace: istio-system
spec:
  ingressClassName: nginx
  rules:
    - host: kiali.localtest.me
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: kiali
                port: { number: 20001 }
```

```bash
kubectl apply -f deploy/platform/kiali-ingress.yaml
```

Open <http://kiali.localtest.me>. Generate traffic first — an idle mesh draws an empty graph, which looks identical to a broken install:

```bash
for i in $(seq 1 50); do
  curl -sS -o /dev/null -X POST http://shop.localtest.me/orders \
    -H 'content-type: application/json' \
    -d '{"customer":"ada","sku":"WIDGET-1","quantity":1,"amount_cents":100}'
done
```

Then, in **Graph**, select the `shop` and `floci` namespaces and turn on the **Security** display option. What you are looking for, in order:

| What you see | What it means |
|---|---|
| A padlock on the `order-api → floci` edge | mTLS is actually in use on that hop — not just configured, *observed*. |
| `ingress-nginx → order-api` present | The edge is enrolled and its traffic is being reported. If nginx is missing from the graph, it never got a sidecar. |
| No edge between `order-api` and `order-worker` | Correct, and worth staring at. They are joined by Kafka, which is outside the mesh, so the mesh cannot draw that relationship. **A service graph is not an architecture diagram** — it shows synchronous calls the proxies saw, and it is blind to your entire async path. |
| Red edges into `floci` | The `deny-all` in §9.5 is doing its job to something. Click the edge → **Traffic** to see which principal was refused. |

The other tab worth your time is **Istio Config**, which validates every `PeerAuthentication`, `AuthorizationPolicy` and `DestinationRule` in the cluster and flags the ones that reference workloads or service accounts that don't exist. That is the exact failure mode §9.5 warned about — a policy whose `principals` have a typo denies everything and looks, from `kubectl get pods`, like a perfectly healthy cluster.

```bash
git add deploy/platform/kiali-ingress.yaml
git commit -m "feat(observability): kiali"
```

> **Kiali is a read-mostly tool, and that's the discipline.** It will happily let you edit Istio config through the UI. Don't: every object it manages is in git, and a change made in the console is a change Argo CD will revert on its next sync — or worse, won't, because you edited something Argo doesn't track. Use it to see and to validate; make changes in the repo.

---

## Where you are

Prometheus scrapes both services, Grafana shows orders moving through the system, and one alert
fires on a symptom a user would notice rather than on a cause you happened to think of.

You still deploy by hand.

**Next: [Phase 3 — Delivery](#).** With a dashboard in front of you, automating
deploys stops being reckless — you will be able to see what each one did.

[← All phases](docs/README.md) · [← Phase 1 — The application, running](#) · [Phase 3 — Delivery: git as the deploy button →](#)

## 11. Argo CD: pull-based delivery


### 11.1 Why pull beats push


The push model: CI holds cluster credentials and runs `kubectl apply` / `helm upgrade`.

The pull model: an agent in the cluster watches git and converges the cluster onto it.

Pull wins on four counts:

1. **Credentials.** CI never gets cluster admin. Your build system is internet-facing and runs arbitrary code from pull requests; giving it production credentials is how supply-chain compromises become production compromises.
2. **Drift.** Argo CD continuously compares live state to git and reports `OutOfSync`. Push-based CD is blind between deploys — someone's emergency `kubectl edit` is invisible until the next release silently reverts it.
3. **Disaster recovery.** The cluster's desired state is a git repo. Rebuilding is "point a new Argo CD at the same repo."
4. **Audit.** Every change is a commit with an author and a review. `kubectl apply` from a laptop is not.

The cost is real: deploys are now asynchronous. CI finishes with "commit pushed", not "deployed". You need Argo's UI or CLI to answer "is it live yet?", and a failed deploy surfaces in a different tool than the build that caused it. Teams that dislike GitOps almost always dislike exactly this.

### 11.2 Install


```bash
kubectl create namespace argocd

kubectl apply -n argocd --server-side --force-conflicts \
  -f https://raw.githubusercontent.com/argoproj/argo-cd/v3.4.7/manifests/install.yaml

kubectl -n argocd rollout status deployment/argocd-server --timeout=300s
kubectl -n argocd get pods
```

> `--server-side` is not optional. Argo CD's CRDs exceed the 262 KB annotation limit that client-side apply uses to store the last-applied configuration, and a client-side apply fails with a confusing metadata error. `--force-conflicts` lets server-side apply take ownership of fields on re-apply.

> **Pin the version, never use `stable`.** `stable` moves under you; a `kubectl apply` six months from now would silently upgrade Argo CD mid-incident. Pin, test upgrades deliberately.

Expose the UI:

**`deploy/platform/argocd-ingress.yaml`**

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: argocd-server
  namespace: argocd
  annotations:
    # argocd-server terminates TLS itself, so nginx must speak HTTPS upstream.
    nginx.ingress.kubernetes.io/backend-protocol: "HTTPS"
    nginx.ingress.kubernetes.io/ssl-passthrough: "false"
spec:
  ingressClassName: nginx
  rules:
    - host: argocd.localtest.me
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: argocd-server
                port: { name: https }
```

```bash
kubectl apply -f deploy/platform/argocd-ingress.yaml
```

Get the initial admin password:

```bash
kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath='{.data.password}' | base64 -d && echo
```

Open <https://argocd.localtest.me>, log in as `admin`. Your browser will warn about the certificate — expected, Argo CD self-signs.

> **`https`, not `http`, and this one is a trap.** We deploy `argocd-server` in its default TLS mode
> (no `--insecure`, `server.insecure` unset in `argocd-cmd-params-cm`), and the Ingress above sets
> `backend-protocol: HTTPS`, so nginx terminates the browser's TLS and re-originates to Argo CD.
> Argo CD therefore marks its `argocd.token` cookie `Secure`. Over plain `http://` the login page
> renders fine and the password is accepted — but the browser silently discards a `Secure` cookie,
> so the next request arrives unauthenticated and you are bounced back to `/login`. **Forever, with
> no error anywhere**: not in the browser, not in `kubectl logs deploy/argocd-server`. An endless
> login redirect on `http://` is this and nothing else.

Install the CLI (useful, and required for one step below):

```bash
brew install argocd

argocd login argocd.localtest.me --username admin \
  --password "$(kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d)" \
  --insecure --grpc-web
```

Delete the bootstrap secret once you've changed the password — it's a static credential with no expiry:

```bash
argocd account update-password
kubectl -n argocd delete secret argocd-initial-admin-secret
```

### 11.3 Give Argo CD access to the repo


If your repo is public, skip this. If private:

```bash
argocd repo add https://github.com/<your-github-user>/modern-devops.git \
  --username <your-github-user> \
  --password <a-github-personal-access-token-with-repo-scope>
```

> In production this credential is itself an `ExternalSecret` sourced from OpenBao, in the `argocd` namespace, targeting a Secret labelled `argocd.argoproj.io/secret-type: repository`. We're doing it imperatively to keep the bootstrap linear — but note the pattern: *the GitOps tool's own config should also be GitOps'd*, and the only thing you're allowed to do by hand is the seed.

### 11.4 The app-of-apps


> **First, hand over what you installed by hand.** In [§10.5](#105-install-it)
> you ran `helm install order-platform` yourself. Argo CD is about to manage the same objects from
> git, and two owners for one Deployment is a fight nobody wins — Helm's release metadata says one
> thing, Argo's desired state says another, and you get a resource that flaps or a sync that never
> converges.
>
> ```bash
> helm uninstall order-platform -n shop
> kubectl -n shop get pods          # empty; Argo CD is about to put them back
> ```
>
> Deleting a working deployment to let a controller recreate it feels wrong the first time. Sit with
> it — that discomfort is exactly the shift from *"I deploy"* to *"git is the source of truth and
> something else deploys"*, and it is the point of this phase. If Argo CD cannot recreate it from the
> repo, then the repo was never a truthful description of your platform and it is much better to find
> that out now, deliberately, than during an incident.

Rather than clicking "New App" in the UI, we declare Applications as YAML, and declare **one** Application whose job is to apply the others. That's the "app of apps" pattern: a single `kubectl apply` bootstraps everything, and adding a component later is a git commit.

**`deploy/argocd/root.yaml`**

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: root
  namespace: argocd
  finalizers:
    # Cascade deletion: removing this Application removes the children it created.
    - resources-finalizer.argocd.argoproj.io
spec:
  project: default
  source:
    repoURL: https://github.com/<your-github-user>/modern-devops.git
    targetRevision: main
    path: deploy/argocd/apps
  destination:
    server: https://kubernetes.default.svc
    namespace: argocd
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
```

**`deploy/argocd/apps/order-platform.yaml`**

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: order-platform
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: default
  source:
    repoURL: https://github.com/<your-github-user>/modern-devops.git
    targetRevision: main
    path: deploy/charts/order-platform
    helm:
      valueFiles:
        - ../../env/local/values.yaml
  destination:
    server: https://kubernetes.default.svc
    namespace: shop
  syncPolicy:
    automated:
      prune: true      # delete resources removed from git
      selfHeal: true   # revert manual kubectl changes
    syncOptions:
      - CreateNamespace=true
      - ServerSideApply=true
    retry:
      limit: 5
      backoff: { duration: 10s, factor: 2, maxDuration: 3m }
```

**`deploy/argocd/apps/platform.yaml`** — the infrastructure we applied by hand, now under GitOps:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: platform
  namespace: argocd
  annotations:
    # Diff by dry-run server-side apply instead of comparing the rendered
    # manifest to the live object. The ExternalSecrets CRD defaults a pile of
    # fields the API server injects — deletionPolicy, engineVersion,
    # mergePolicy, conversionStrategy, decodingStrategy, metadataPolicy,
    # nullBytePolicy — none of which are in git. A client-side diff sees them
    # as drift and parks this Application on OutOfSync forever, while
    # `kubectl diff` (which is already server-side) reports no difference at
    # all. Requires ServerSideApply, which is set below.
    argocd.argoproj.io/compare-options: ServerSideDiff=true
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: default
  source:
    repoURL: https://github.com/<your-github-user>/modern-devops.git
    targetRevision: main
    path: deploy/platform
    directory:
      recurse: true
      # Argo CD would otherwise try to own the Argo CD Ingress it is serving
      # from. Excluding it avoids a self-referential sync.
      exclude: "argocd-ingress.yaml"
  destination:
    server: https://kubernetes.default.svc
    namespace: default
  syncPolicy:
    automated: { prune: false, selfHeal: true }
    syncOptions:
      - CreateNamespace=true
      - ServerSideApply=true
```

> **`prune: false` on platform, `prune: true` on the app.** Pruning is what makes git authoritative — delete a manifest, the object disappears. That's correct for application workloads. For shared infrastructure it's a footgun: a bad rebase that drops a file would delete your Kafka cluster and its PVCs. Different blast radius, different setting. Decide this per-Application, deliberately.

> **Every CRD an Application references must already exist when it syncs.** Argo CD does not skip a
> resource whose CRD is missing — it fails the entire Application, so one unrecognised `PodMonitor`
> leaves every workload in `shop` reported as `Missing`. The chart's `serviceMonitor` and `podMonitor`
> toggles both default to `false` for exactly this reason and are flipped only once
> [§13.2](#132-install) has installed the `monitoring.coreos.com` CRDs. The
> same rule applies to anything else you add under `deploy/platform`: operator first, custom resources
> second.

> **`selfHeal: true` means `kubectl edit` is now temporary.** Argo reverts your change within seconds. This is the correct default and it will infuriate you the first time you're debugging live. The escape hatch is `argocd app set <app> --sync-policy none` for the duration of the incident — do that consciously rather than fighting the controller.

Push and bootstrap:

```bash
git add deploy/ && git commit -m "feat(argocd): app-of-apps bootstrap"
git push

kubectl apply -f deploy/argocd/root.yaml
argocd app list
```

`order-platform` will go `Progressing` → likely `Degraded`, because the image tag is `dev` and nothing has pushed `nexus:8082/shop/order-api:dev` yet. That's expected and correct — Argo CD is faithfully reporting that the desired state is unachievable. CI fixes it in the next section.

Watch it:

```bash
argocd app get order-platform
kubectl -n shop get pods
```

---

## 12. Buildkite: CI that runs on your infrastructure


### 12.1 The hybrid model, and its one honest caveat


Buildkite splits CI into two halves:

- **The control plane** (buildkite.com) holds pipeline definitions, schedules jobs, and renders the UI. SaaS.
- **The agents** run on your compute, inside your network. They poll the control plane for work over an outbound HTTPS connection.

The consequence: **no inbound firewall holes, and your build secrets never leave your infrastructure.** The control plane knows a job ran and whether it passed; it never sees your source, your registry credentials, or your artifacts. That's why Buildkite shows up in regulated environments where "paste your production credentials into a SaaS vault" is a non-starter.

> **The caveat, stated plainly: there is no offline Buildkite.** The control plane is a hosted service. Every other component in this tutorial runs entirely on your laptop; this one does not. If your goal is a fully air-gapped lab, substitute Woodpecker CI or Concourse and adapt [§12.5](#125-the-pipeline) — the pipeline shape (test → build → push → commit a tag) is portable, and so is generating it from a script; only the YAML dialect the script emits is not.

The free tier is sufficient for everything here.

### 12.2 Create the Buildkite side


1. Sign up at <https://buildkite.com>, create an organization.
2. **Agents → Clusters**. A cluster is a pool of agents with its own tokens and queues. Create one named `local`.
3. Inside `local`, go to **Queues** and confirm a queue named `default` exists. Create a queue named **`kubernetes`** — our agent stack advertises this tag, and steps target it. On the *"Select your agent infrastructure"* step the form defaults to **Hosted**; you **must** change it to **Self-hosted**, because a hosted queue runs jobs on Buildkite's machines instead of your cluster and the infrastructure type cannot be changed after the queue is created.
4. Go to **Agent tokens → New token**, description `kind-devops`. **Copy the token now** — it is shown once.
5. **Pipelines → New pipeline**:
   - Name: `order-platform`
   - Repository: `https://github.com/<your-github-user>/modern-devops.git`
   - Cluster: `local`
   - Under **Steps**, replace the default with:
     ```yaml
     steps:
       - label: ":pipeline:"
         agents: { queue: kubernetes }
         command: ".buildkite/upload.sh"
     ```
   - Create the pipeline. Buildkite will offer to add a GitHub webhook — accept it, authorising the GitHub App when prompted.

> **Why the UI-side pipeline is one step.** The pipeline stored in Buildkite's UI is a bootstrap; the real definition is *generated* by `.buildkite/pipeline.sh` **in your repo** ([§12.5](#125-the-pipeline)). That means pipeline changes are reviewed in PRs alongside the code they build, and a branch can change its own build. Never grow the UI-side pipeline beyond this step.

> **`agents: { queue: kubernetes }` is not optional.** Every job in a cluster is assigned to a queue, and a step with no `queue` tag lands on the cluster's *default* queue. Our agent stack ([§12.3](#123-install-the-agent-stack-in-kubernetes)) advertises `queue=kubernetes` only, so an untagged bootstrap step sits in the `default` queue forever with no agent to run it — a build stuck at "waiting for agent" with no error.

Export the token for the next section:

```bash
export BUILDKITE_AGENT_TOKEN='<paste-the-agent-token>'
```

### 12.3 Install the agent stack in Kubernetes


`agent-stack-k8s` is a controller: it watches Buildkite for jobs tagged with your queue and creates a Kubernetes **Job** per build step. Each step gets a fresh pod, so builds are isolated by construction — no leftover state, no "works on agent-3 only".

```bash
kubectl create namespace buildkite

kubectl create secret generic buildkite-agent-token -n buildkite \
  --from-literal=BUILDKITE_AGENT_TOKEN="$BUILDKITE_AGENT_TOKEN"
```

> The key **must** be exactly `BUILDKITE_AGENT_TOKEN`. The controller looks it up by name.

Git credentials, so the checkout container can clone (and the deploy step can push). Create a GitHub **fine-grained personal access token** with `Contents: Read and write` on this one repository:

```bash
export GITHUB_USER='<your-github-user>'
export GITHUB_TOKEN='<your-fine-grained-PAT>'

printf 'https://%s:%s@github.com\n' "$GITHUB_USER" "$GITHUB_TOKEN" > /tmp/.git-credentials

kubectl create secret generic git-https-credentials -n buildkite \
  --from-file=.git-credentials=/tmp/.git-credentials

shred -u /tmp/.git-credentials 2>/dev/null || rm -f /tmp/.git-credentials
```

> **A repo-scoped, write-capable token now lives in the cluster.** Scope it to the single repository, never to the org. In production this comes from OpenBao through ESO exactly like the Nexus credential — we're doing it imperatively only because Buildkite must be able to clone before it can run the pipeline that would otherwise create it. **Bootstrap always has one manual seed; the discipline is keeping it to one.**

Now the Helm install:

**`infra/buildkite-values.yaml`**

```yaml
agentStackSecret: buildkite-agent-token

config:
  tags:
    - queue=kubernetes
  # Applies to every job's checkout container, so we don't repeat it per-step.
  default-checkout-params:
    gitCredentialsSecret:
      secretName: git-https-credentials
```

```bash
helm upgrade --install agent-stack-k8s \
  oci://ghcr.io/buildkite/helm/agent-stack-k8s \
  --version 0.46.3 \
  --namespace buildkite \
  --values infra/buildkite-values.yaml \
  --wait

kubectl -n buildkite get pods
kubectl -n buildkite logs deploy/agent-stack-k8s --tail=20
```

The log should show the controller connecting and polling. In the Buildkite UI, **Agents** will show a connected agent for cluster `local`.

### 12.4 Credentials the build itself needs


The build needs the Nexus credential twice, in two different shapes: Buildah reads a plain auth file
to *push* images, and the kubelet needs a `kubernetes.io/dockerconfigjson` Secret to *pull* the CI
image the verify step runs in. Both come from the same OpenBao entry, in the `buildkite` namespace.

**`deploy/platform/buildkite-secrets.yaml`**

```yaml
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: nexus-push
  namespace: buildkite
spec:
  refreshInterval: "1h"
  secretStoreRef:
    name: openbao
    kind: ClusterSecretStore
  target:
    name: nexus-push
    creationPolicy: Owner
    template:
      # Buildah reads a plain auth file, not a Kubernetes dockerconfigjson type.
      # Same JSON shape, different Secret type - so we template it as Opaque.
      type: Opaque
      data:
        config.json: |
          {
            "auths": {
              "nexus:8082": {
                "auth": "{{ printf "%s:%s" .username .password | b64enc }}"
              }
            }
          }
  data:
    - secretKey: username
      remoteRef: { key: nexus, property: username }
    - secretKey: password
      remoteRef: { key: nexus, property: password }

---
# Any build step that runs an image out of Nexus needs the kubelet in this
# namespace to hold credentials of its own. nexus-push above is Opaque — a
# Buildah auth file — and the kubelet cannot use it as an imagePullSecret; that
# requires the kubernetes.io/dockerconfigjson type. Same credential, different
# Secret type, because two different consumers want two different shapes.
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: nexus-pull
  namespace: buildkite
spec:
  refreshInterval: "1h"
  secretStoreRef:
    name: openbao
    kind: ClusterSecretStore
  target:
    name: nexus-pull
    creationPolicy: Owner
    template:
      type: kubernetes.io/dockerconfigjson
      data:
        .dockerconfigjson: |
          {
            "auths": {
              "nexus:8082": {
                "username": "{{ .username }}",
                "password": "{{ .password }}",
                "auth": "{{ printf "%s:%s" .username .password | b64enc }}"
              }
            }
          }
  data:
    - secretKey: username
      remoteRef: { key: nexus, property: username }
    - secretKey: password
      remoteRef: { key: nexus, property: password }
```

```bash
kubectl apply -f deploy/platform/buildkite-secrets.yaml
kubectl -n buildkite get externalsecret          # both SecretSynced=True
kubectl -n buildkite get secret nexus-push -o jsonpath='{.data.config\.json}' | base64 -d | jq .
kubectl -n buildkite get secret nexus-pull -o jsonpath='{.data.\.dockerconfigjson}' | base64 -d | jq .
```

> **Secrets do not cross namespaces.** `nexus-pull` already exists in `shop`
> ([§7.6](#76-let-kubernetes-pull-from-nexus)), and that instance is invisible from
> `buildkite`. Every namespace that pulls from Nexus needs its own copy, which is why the
> `ExternalSecret` is duplicated rather than shared.

### 12.5 The pipeline


A Buildkite pipeline does not have to be a file. `buildkite-agent pipeline upload` reads YAML on **stdin**, so the definition can be *generated* at the start of a build by a script that knows things a static file cannot: which commit this is, what it changed, and whether it is worth building at all. That is a **dynamic pipeline**, and it is the shape we use.

> **Why a generator instead of a static `pipeline.yml`.** Three concrete wins, in the order they matter here.
> 1. **The loop guard runs before any pod starts.** A deploy commit now produces a one-step pipeline instead of running the full test-and-build cycle and throwing the result away at the end.
> 2. **The two Buildah steps stop being copy-paste.** They differed only in a service name; as hand-maintained twins they drift, and the drift is silent. One template in a `for` loop cannot drift.
> 3. **No `$$` escaping anywhere.** The generator substitutes the commit SHA and registry host as it writes the YAML, so the emitted pipeline contains no `$` at all. Buildkite's upload-time interpolation of `$VAR`/`${VAR}` — the classic source of silently-empty variables — has nothing left to bite.
>
> The price, stated plainly: a YAML syntax error in a static pipeline is caught before the build starts; in a generated one, the bad YAML appears mid-build. `.buildkite/upload.sh` below buys most of that back with a dry-run.

**`.buildkite/pipeline.sh`**

```sh
#!/bin/sh
# Emits this build's pipeline as YAML on stdout. It talks to nothing and
# changes nothing - run it locally and read what it prints.
#
# POSIX sh, deliberately: this runs in the default agent image, whose only
# guaranteed shell is /bin/sh.
set -eu

REGISTRY="nexus:8082"
# A build triggered by hand in the UI sets BUILDKITE_COMMIT to the literal
# string "HEAD" rather than a SHA, which would tag images `:HEAD` — a mutable
# tag that means a different image on every build, and the exact thing §10.3
# says a tag must never be. Resolve it to a real SHA before it reaches a tag.
if [ "$BUILDKITE_COMMIT" = "HEAD" ]; then
  BUILDKITE_COMMIT="$(git rev-parse HEAD)"
fi
SHA="$(echo "$BUILDKITE_COMMIT" | cut -c1-12)"

case "$SHA" in
  *[!0-9a-f]*|"") echo "refusing to build: BUILDKITE_COMMIT is not a SHA ($BUILDKITE_COMMIT)" >&2; exit 1 ;;
esac

# Services are discovered, not listed. A directory under services/ with a
# Dockerfile in it is a service, and that is the entire contract. This is what
# lets the Backstage paved path (§14.6) add a service without touching CI.
SERVICES="$(cd services && ls -d */ 2>/dev/null | sed 's#/##' | while read -r s; do
  [ -f "$s/Dockerfile" ] && echo "$s"
done | sort | tr '\n' ' ')"

if [ -z "$SERVICES" ]; then
  echo "no services found under services/*/Dockerfile" >&2
  exit 1
fi

# ── LOOP GUARD ─────────────────────────────────────────────────────────────
# The deploy step at the bottom commits into the repo we build from, so
# without this every deploy triggers a build that makes another deploy,
# forever. Deciding it here, before any step exists, is the whole reason this
# is a script.
if git log -1 --pretty=%s | grep -q '^chore(deploy):'; then
  cat <<'YAML'
steps:
  - label: ":fast_forward: deploy commit, nothing to build"
    agents: { queue: kubernetes }
    command: "echo 'HEAD is a deploy commit; skipping'"
YAML
  exit 0
fi

# ── Header ─────────────────────────────────────────────────────────────────
# Every step runs in its own Kubernetes pod, created by agent-stack-k8s.
# The `kubernetes` plugin is how a step describes the pod it wants.
cat <<'YAML'
env:
  # Nexus proxies. Builds never talk to pypi.org or proxy.golang.org directly:
  # that is the supply-chain choke point from §5.1, made real.
  # pip needs these to install uv itself. uv does NOT get its index from here:
  # it reads [[tool.uv.index]] in services/order-api/pyproject.toml, so the
  # registry is recorded in uv.lock and `--locked` validates the same way on a
  # laptop and in this pod. Setting UV_DEFAULT_INDEX here instead would put the
  # index in CI only, and the committed lock would never match it.
  PIP_INDEX_URL: "http://nexus:8081/repository/pypi-proxy/simple"
  PIP_TRUSTED_HOST: "nexus"
  GOPROXY: "http://nexus:8081/repository/go-proxy"
  # The public checksum database is unreachable through a private proxy, so
  # verification must be turned off for modules the proxy serves. In production
  # you run an internal sumdb or vendor dependencies instead of disabling this.
  GOSUMDB: "off"
  GONOSUMDB: "*"
  GOFLAGS: "-mod=mod"

steps:
  # ── 1. Tests, in parallel ────────────────────────────────────────────────
  - label: ":python: test order-api"
    key: test-api
    agents: { queue: kubernetes }
    plugins:
      - kubernetes:
          podSpec:
            containers:
              - image: python:3.13-slim
                command:
                  - |
                    set -euo pipefail
                    cd services/order-api
                    pip install --quiet uv
                    uv sync --locked --dev
                    uv run ruff check .
                    uv run pytest -q

  - label: ":go: test order-worker"
    key: test-worker
    agents: { queue: kubernetes }
    plugins:
      - kubernetes:
          podSpec:
            containers:
              # Debian, not alpine: `go test -race` needs cgo, and the alpine
              # image ships CGO_ENABLED=0 with no C toolchain. Adding gcc and
              # musl-dev to alpine also works; this is one word instead.
              - image: golang:1.26
                command:
                  - |
                    set -euo pipefail
                    cd services/order-worker
                    go vet ./...
                    go test -race ./...

  - wait
YAML

# `golang:1.26` and not `golang:1.26-alpine` for the TEST step specifically:
#
#   golang:1.26-alpine : CGO_ENABLED=0, no gcc
#   golang:1.26        : CGO_ENABLED=1, gcc 14.2.0, git 2.47.3
#
# `go test -race` is implemented with a C runtime, so on alpine it refuses with
# `go: -race requires cgo; enable cgo by setting CGO_ENABLED=1` — and setting
# that variable alone doesn't help, because there is no compiler to use. The
# Dockerfile in §3.2 still builds FROM golang:1.26-alpine, and should: there we
# *want* CGO_ENABLED=0 for a static binary in a scratch image. Test and build
# want opposite things from the same toolchain, which is why they differ.

# ── 2. Build and push images ───────────────────────────────────────────────
# One template, one step per service. When these were two hand-maintained
# YAML blocks they differed only in a name, which is exactly the kind of
# duplication that drifts without anyone noticing.
for SVC in $SERVICES; do
  # Only the Go image takes a version stamp (services/order-worker/Dockerfile
  # declares ARG VERSION); buildah warns about build-args the Dockerfile never
  # declares, so don't pass it to the Python one.
  case "$SVC" in
    order-worker) BUILD_ARGS="--build-arg \"VERSION=$SHA\" " ;;
    *)            BUILD_ARGS="" ;;
  esac

  cat <<YAML

  - label: ":docker: build $SVC ($SHA)"
    key: build-$SVC
    agents: { queue: kubernetes }
    plugins:
      - kubernetes:
          podSpec:
            volumes:
              - name: nexus-auth
                secret: { secretName: nexus-push }
            containers:
              - image: quay.io/buildah/stable:v1.40.1
                # See the securityContext note below. This is a real trade.
                securityContext:
                  privileged: true
                env:
                  - name: STORAGE_DRIVER
                    value: vfs
                  - name: BUILDAH_FORMAT
                    value: docker
                  - name: REGISTRY_AUTH_FILE
                    value: /auth/config.json
                volumeMounts:
                  - name: nexus-auth
                    mountPath: /auth
                    readOnly: true
                command:
                  - |
                    set -euo pipefail

                    buildah bud \\
                      --tls-verify=false \\
                      ${BUILD_ARGS}--file services/$SVC/Dockerfile \\
                      --tag "$REGISTRY/shop/$SVC:$SHA" \\
                      --tag "$REGISTRY/shop/$SVC:latest" \\
                      services/$SVC

                    buildah push --tls-verify=false "$REGISTRY/shop/$SVC:$SHA"
                    buildah push --tls-verify=false "$REGISTRY/shop/$SVC:latest"

                    echo "pushed $REGISTRY/shop/$SVC:$SHA"
YAML
done

# ── 3. The handoff to CD: write the tag into git ───────────────────────────
cat <<YAML

  - wait

  - label: ":git: bump image tags to $SHA"
    key: deploy
    branches: "main"
    agents: { queue: kubernetes }
    plugins:
      - kubernetes:
          checkout:
            gitCredentialsSecret:
              secretName: git-https-credentials
          podSpec:
            volumes:
              - name: git-creds
                secret: { secretName: git-https-credentials }
            containers:
              - image: alpine/git:2.47.2
                volumeMounts:
                  - name: git-creds
                    mountPath: /gitcreds
                    readOnly: true
                command:
                  - |
                    set -eu
                    git config user.name  "buildkite"
                    git config user.email "buildkite@localtest.me"
                    git config credential.helper "store --file=/gitcreds/.git-credentials"

                    # The overlay has exactly one job - carry the two tags - so
                    # rewriting it wholesale is deterministic and needs no yq.
                    # The tags are literals: pipeline.sh already resolved them.
                    cat > deploy/env/local/values.yaml <<'VALUES'
                    # Generated by Buildkite. Do not edit by hand.
                    orderApi:
                      image:
                        tag: "$SHA"
                    orderWorker:
                      image:
                        tag: "$SHA"
                    # Every scaffolded service (§14.6) is built from this same
                    # commit, so one tag covers all of them.
                    scaffolded:
                      tag: "$SHA"
                    VALUES

                    git add deploy/env/local/values.yaml
                    if git diff --cached --quiet; then
                      echo "no change; nothing to deploy"
                      exit 0
                    fi

                    git commit -m "chore(deploy): order-platform $SHA [skip ci]"
                    git push origin HEAD:main
                    echo "pushed deploy commit; Argo CD will sync"
YAML
```

**`.buildkite/upload.sh`** — the bootstrap the UI-side step runs.

```sh
#!/bin/sh
# Generate, validate, keep a copy, then upload. The dry-run is what a static
# pipeline gives you for free and a generated one does not: it rejects invalid
# YAML before any of it becomes real steps.
set -eu

.buildkite/pipeline.sh > /tmp/pipeline.yml

buildkite-agent pipeline upload --dry-run < /tmp/pipeline.yml > /dev/null
buildkite-agent artifact upload /tmp/pipeline.yml
buildkite-agent pipeline upload /tmp/pipeline.yml
```

> **Note the missing pipe.** The obvious form is `.buildkite/pipeline.sh | buildkite-agent pipeline upload`, and it hides failures: in a pipe, the exit status is the *last* command's, so a generator that dies half-way still uploads whatever it managed to print, and the step goes green. Writing to a file under `set -e` makes a broken generator fail the build. The artifact upload is not decoration either — when a build does something surprising, the exact YAML that produced it is attached to the build.

Make them executable, or the agent gets "permission denied" and you lose ten minutes:

```bash
chmod +x .buildkite/pipeline.sh .buildkite/upload.sh
```

You can read the pipeline any time without pushing anything:

```bash
BUILDKITE_COMMIT="$(git rev-parse HEAD)" .buildkite/pipeline.sh
```

Five things in there deserve explanation.

**The image tag is the commit SHA, never `latest`.** `latest` is a mutable pointer: two clusters can run different code while both claim to run `latest`, and rollback is undefined. The SHA makes "what is running" and "what is in git" the same question. We also push `latest` as a convenience pointer for humans — nothing in the deployment path reads it.

**CI never touches the cluster.** The final step's total privilege is: push a commit to one repo. It has no kubeconfig, no cluster token, no `helm` binary. If this pipeline is compromised, the attacker gets a commit — which is reviewable and revertible — not cluster admin. Compare that to `helm upgrade` in CI.

**`privileged: true` on the Buildah containers is the ugliest line in this tutorial.** Building OCI images needs mount and user-namespace operations that a default-restricted container cannot perform. The honest options: (a) privileged, which is what we do, and which means a malicious `Dockerfile` can escape to the node; (b) rootless Buildah with correct `/etc/subuid` mapping and a `seccomp: unconfined` annotation — fiddly and version-sensitive; (c) a remote BuildKit daemon on dedicated hardware, so build pods hold no privilege at all — the correct production answer; (d) user namespaces, which make this genuinely safe and are still stabilising in Kubernetes. **If you take one thing into production from this section, take: builds run on isolated node pools, never alongside workloads.**

**The loop guard exists because we chose a mono-repo.** CI commits to the repo CI builds from, so without a guard every deploy triggers a build that triggers a deploy, forever. We break it two ways, belt and braces: the commit subject carries `[skip ci]`, and `pipeline.sh` emits a no-op pipeline when `HEAD` is already a `chore(deploy):` commit. With split app/config repos this problem simply does not exist — which is the strongest practical argument for splitting them, and worth more than the convenience the mono-repo bought us.

**Quoted heredocs are load-bearing.** `<<'YAML'` passes text through untouched; `<<YAML` lets the generator substitute `$SHA`, `$SVC` and `$REGISTRY`. Get the quoting backwards on the first block and `$$`-style text meets `sh`, where `$$` is the process ID — you would emit an image name like `/shop/order-api:8412REGISTRY` and spend an afternoon on it. The rule: quote the heredoc unless that block needs a value from the generator, and never emit a literal `$` — resolve it while writing the YAML instead.

> **The obvious next step, and why it isn't here.** A generator can also decide *what changed* — `git diff --name-only` against the merge base, then emit build steps only for the services it touched. We don't, because `deploy/env/local/values.yaml` carries both tags at once: skip the `order-worker` build and the deploy step still stamps this SHA on both images, so Kubernetes pulls an `order-worker` tag that was never pushed and you get `ImagePullBackOff`. Per-service builds need per-service tags in the overlay first. Fix the contract, then optimise the pipeline — never the other way round.

### 12.6 Run it


```bash
git add .buildkite deploy/platform/buildkite-secrets.yaml infra/buildkite-values.yaml
git commit -m "ci: buildkite pipeline"
git push

# Confirm the exec bits made it into git - 100755, not 100644.
git ls-files -s .buildkite
```

Watch the build in the Buildkite UI. The first job you see is the bootstrap; the rest of the pipeline appears the moment it uploads. Simultaneously watch pods appear and vanish:

```bash
kubectl -n buildkite get pods -w
```

When the pipeline goes green, the deploy commit lands and Argo CD picks it up within its polling interval (3 minutes by default). Force it if you're impatient:

```bash
argocd app sync order-platform
argocd app get order-platform
kubectl -n shop get pods
```

You should see every workload the chart enables Running, on images tagged with your commit SHA:

```bash
kubectl -n shop get deploy -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.template.spec.containers[0].image}{"\n"}{end}'
```

> **Reduce Argo's 3-minute latency properly.** The polling interval is a compromise between responsiveness and load on your git provider. The production fix is not a shorter interval — it's a **webhook** from GitHub to `argocd-server/api/webhook`, which makes syncs event-driven and near-instant. That needs an inbound URL, which your laptop doesn't have, so we poll. Know that polling is the fallback, not the design.

---

## Where you are

A push to `main` runs tests, builds images through your own registry, writes the resulting tag into
git, and Argo CD deploys it. No human types `helm upgrade`. No CI job holds a kubeconfig.

What is still true, and is about to stop being true: **every workload in this cluster trusts every
other workload, because they can reach each other.**

**Next: [Phase 4 — Identity between services](#).**

[← All phases](docs/README.md) · [← Phase 2 — Seeing what it does](#) · [Phase 4 — Identity between services →](#)

## 9. Istio: the service mesh


### 9.1 What a mesh actually buys you here — and what it doesn't


Start with the uncomfortable part. The usual service-mesh demo has service A calling service B over HTTP, and mTLS between them is the punchline. **We don't have that shape.** `order-api` never calls `order-worker`; Kafka joins them, asynchronously and deliberately ([§8](#8-kafka-with-strimzi)). If you install a mesh here expecting the demo, you get an expensive no-op.

What Istio does secure and observe in *this* topology:

| Path | Protocol | In the mesh? |
|---|---|---|
| ingress-nginx → `order-api` | HTTP | yes, once nginx is enrolled |
| `order-api` → Floci (S3, DynamoDB) | HTTP (AWS API) | yes |
| `order-worker` → Floci | HTTP (AWS API) | yes |
| `order-api` → Kafka | Kafka wire protocol over TCP | no — see below |
| Prometheus → app `/metrics` | HTTP | no — and that's a problem we have to solve, §9.6 |

So the honest pitch: the mesh gives you **identity-based mTLS on every HTTP hop we have, an authorization policy that survives a stolen pod IP, and L7 telemetry for calls whose code you don't control** (the AWS SDK's calls to Floci are the interesting case — you get per-route latency and error rates without touching either service).

> **Tradeoff — sidecar vs ambient.** We use sidecars: an Envoy injected into each pod. It is the mode with the deepest documentation, and `VirtualService`/`DestinationRule` work with no extra hop. The cost is real and you will feel it on a laptop: one extra container and roughly 50–100 MB per pod, plus a restart of every workload to enroll it. Istio's newer **ambient** mode replaces per-pod sidecars with one `ztunnel` per node and would cost a fraction of that RAM, at the price of needing an explicit waypoint proxy before any L7 policy works. If you are RAM-constrained, ambient is the better laptop choice; we take sidecars because the mental model matches the documentation you'll hit everywhere else.

> **We keep ingress-nginx as the edge.** Istio can serve north-south traffic itself, and in production that is usually the right call — one proxy, one config language. Here nginx already owns `hostPort` 80/443 on the kind control-plane node ([§4.3](#43-install-the-ingress-controller)), and swapping it out means rewriting every `Ingress` in the tutorial as an `HTTPRoute` and recreating the cluster. We keep nginx and **enroll it into the mesh** instead, which is the documented way to put a third-party ingress in front of meshed workloads: nginx terminates the browser's connection and re-originates it as mTLS to `order-api`.

### 9.2 Install the control plane


```bash
helm repo add istio https://istio-release.storage.googleapis.com/charts
helm repo update

kubectl create namespace istio-system

# CRDs and cluster-scoped resources.
helm install istio-base istio/base \
  --namespace istio-system --version 1.30.3 --wait

# The control plane itself.
helm install istiod istio/istiod \
  --namespace istio-system --version 1.30.3 --wait
```

Verify before you enroll anything — a half-installed control plane fails in ways that look like application bugs:

```bash
kubectl -n istio-system get deploy istiod
kubectl -n istio-system logs deploy/istiod --tail=20 | grep -i "ready\|error"
istioctl version
```

> **Two charts, not one, and no `istioctl install`.** `base` carries the CRDs and cluster-scoped RBAC; `istiod` carries the control plane. Splitting them is what makes upgrades controllable: CRDs move forward independently of the deployment that consumes them, and you can roll back one without the other. `istioctl install` is the friendlier command and hides that seam — fine for a demo, wrong for anything you intend to upgrade. We install with Helm because everything else in this cluster is installed with Helm, and one lifecycle tool beats two.

### 9.3 Enroll namespaces — and decide, deliberately, which ones


Injection is per-namespace, and the interesting decisions are the exclusions.

`shop` and `floci` are declared in *our* manifests ([§6.2](#62-deploy-floci-into-the-cluster), [§7.5](#75-install-external-secrets-operator)),
so their labels belong in git and are already there. Only `ingress-nginx` — whose namespace comes from
an upstream manifest we don't own — needs the imperative form:

```bash
kubectl label namespace ingress-nginx istio-injection=enabled --overwrite

kubectl get namespace -L istio-injection
```

> **Put `istio-injection: enabled` in the namespace manifest in git, never on the command line.**
> Once a namespace is under Argo CD, every field of it is — a hand-set label is dropped the next time
> Argo CD recreates the namespace from `deploy/platform/`, and the pods that come back have no sidecar.
> `ingress-nginx` is the exception above only because nothing in `deploy/` declares that namespace.

| Namespace | Enrolled | Why |
|---|---|---|
| `shop` | yes | The workloads whose traffic we actually want identity on. |
| `floci` | yes | It's the callee on both interesting HTTP paths. A policy that says "only these two identities may call S3" is worth having. |
| `ingress-nginx` | yes | So the edge can re-originate browser traffic as mTLS. Without this, STRICT mode in `shop` turns every page load into a connection reset. |
| `kafka` | **no** | Strimzi brokers advertise listener addresses and do their own TLS and rebalancing; putting Envoy in that path is a well-known source of broker-discovery failures for no security gain — Strimzi already offers listener TLS and mTLS auth if you want it. |
| `buildkite` | **no** | Build steps are Kubernetes **Jobs**. A classic sidecar keeps running after the build container exits, so the pod never reaches `Completed` and the job hangs forever. (Kubernetes ≥1.29 native sidecar containers fix this, and Istio can use them — verify it's enabled in your build before relying on it, rather than assuming.) |
| `argocd`, `monitoring`, `istio-system` | **no** | Control-plane components. Injecting your delivery and observability tooling into the mesh means an Istio misconfiguration can take away the tools you'd use to diagnose it. |

Sidecars are injected at pod **creation**, so existing pods need a restart:

```bash
kubectl -n floci rollout restart deployment/floci
kubectl -n ingress-nginx rollout restart deployment/ingress-nginx-controller

# order-api / order-worker don't exist yet — they'll be born with sidecars in §11.
kubectl -n floci get pods          # READY should be 2/2
kubectl -n ingress-nginx get pods  # READY should be 2/2
```

`2/2` is the whole verification: your container plus `istio-proxy`.

One thing in the `floci` namespace must **not** be injected — the bootstrap Job from [§6.3](#63-bootstrap-the-s3-bucket-and-dynamodb-table). That's why its pod template already carries the opt-out:

```yaml
  template:
    metadata:
      annotations:
        sidecar.istio.io/inject: "false"
```

Jobs and classic sidecars do not mix: the build or bootstrap container exits, Envoy keeps running, and the pod sits in `NotReady` forever while `kubectl wait --for=condition=complete` burns its timeout.

> **This is the single most common way a mesh rollout goes wrong**, and it is worth internalising: enrolling a namespace enrolls everything born in it, including Jobs, CronJobs and one-shot migration pods. The blast radius of `kubectl label namespace` is larger than it looks.

### 9.4 mTLS, and proving it is actually on


By default Istio is **PERMISSIVE**: it accepts both mTLS and plaintext, so nothing breaks when you enroll a namespace. That is a migration setting, not a destination — a workload that accepts plaintext is a workload an attacker can talk to in plaintext.

**`deploy/platform/istio/peer-authentication.yaml`**

```yaml
apiVersion: security.istio.io/v1
kind: PeerAuthentication
metadata:
  name: default
  namespace: shop
spec:
  mtls:
    mode: STRICT
---
apiVersion: security.istio.io/v1
kind: PeerAuthentication
metadata:
  name: default
  namespace: floci
spec:
  mtls:
    mode: STRICT
```

Before you apply it, every `Ingress` in the chart needs two annotations. `ingress-nginx` is enrolled
in the mesh and `shop` is about to become STRICT, so the edge has to address its backend in a way
Envoy can identify as a service — by ClusterIP rather than raw pod IPs, and with the upstream `Host:`
rewritten to the service FQDN, because Envoy routes HTTP by authority, not by address. This is the
`order-api` Ingress from [§10.1](#101-one-chart-two-workloads), with the
annotations in place (the chart file carries the same pair under a longer comment); `frontend` and
every scaffolded service carry them too, with their own name substituted:

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: order-api
  annotations:
    # The edge is outside the mesh, the backend is inside it under STRICT mTLS:
    # send to the ClusterIP, and rewrite the upstream Host to the service FQDN
    # so Envoy can match the cluster and originate mTLS to it.
    nginx.ingress.kubernetes.io/service-upstream: "true"
    nginx.ingress.kubernetes.io/upstream-vhost: "order-api.{{ .Release.Namespace }}.svc.cluster.local"
spec:
  ingressClassName: {{ .Values.orderApi.ingress.className }}
  rules:
    - host: {{ .Values.orderApi.ingress.host }}
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: order-api
                port: { name: http }
```

```bash
mkdir -p deploy/platform/istio
kubectl apply -f deploy/platform/istio/peer-authentication.yaml
```

Now prove it, because "I applied a YAML file" is not evidence. Talk to Floci from a pod with no sidecar:

```bash
# From outside the mesh: refused.
kubectl run probe --rm -it --restart=Never --image=curlimages/curl:8.11.1 -- \
  curl -sS --max-time 5 http://floci.floci.svc.cluster.local:4566/_localstack/health
# curl: (56) Recv failure: Connection reset by peer

# From inside the mesh: fine.
kubectl -n floci run probe --rm -it --restart=Never --image=curlimages/curl:8.11.1 -- \
  curl -sS --max-time 5 http://floci.floci.svc.cluster.local:4566/_localstack/health
# {"services": {...}}
```

The first command runs in `default`, which has no injection, so its traffic arrives as plaintext and Envoy drops it. The second runs in `floci`, gets a sidecar, and speaks mTLS without a single line of application code knowing about it. **That difference is the entire value proposition** — identity is a property of the platform, not of your services.

### 9.5 Authorization: deny by default, then allow the paths that exist


mTLS answers *who is calling*. It does not answer *whether they should be*. Any meshed workload can still call Floci with a valid certificate.

**`deploy/platform/istio/authorization-policy.yaml`**

```yaml
# 1. Deny everything in the floci namespace...
apiVersion: security.istio.io/v1
kind: AuthorizationPolicy
metadata:
  name: deny-all
  namespace: floci
spec:
  {}   # An empty spec with no rules is a deny-all. This is not a typo.
---
# 2. ...then allow exactly the two identities that have business there.
apiVersion: security.istio.io/v1
kind: AuthorizationPolicy
metadata:
  name: allow-shop-workloads
  namespace: floci
spec:
  action: ALLOW
  rules:
    - from:
        - source:
            principals:
              - "cluster.local/ns/shop/sa/order-api"
              - "cluster.local/ns/shop/sa/order-worker"
---
# 3. order-api is reachable from the edge, and from nowhere else.
apiVersion: security.istio.io/v1
kind: AuthorizationPolicy
metadata:
  name: allow-ingress-to-order-api
  namespace: shop
spec:
  selector:
    matchLabels:
      app.kubernetes.io/name: order-api
  action: ALLOW
  rules:
    - from:
        - source:
            principals:
              - "cluster.local/ns/ingress-nginx/sa/ingress-nginx"
```

```bash
kubectl apply -f deploy/platform/istio/authorization-policy.yaml
```

> **`principals` is the point.** These rules key on the **SPIFFE identity in the peer's certificate**, not on IP addresses or namespace labels. An attacker who gets a shell in a pod in another namespace cannot reach Floci by spoofing an IP, because they cannot mint a certificate for `sa/order-api`. This is why "the mesh" and "network policy" are not competing answers to the same question: NetworkPolicy filters packets by address, Istio filters requests by cryptographic identity. Use both.

> **The service-account names are load-bearing.** These principals must match the ServiceAccounts the Helm chart creates in [§10.1](#101-one-chart-two-workloads). If the chart names them differently, the policy silently denies everything, and you will debug it as "Floci is down". `istioctl analyze -n shop` catches the mismatch; `kubectl get pods` does not.

### 9.6 The metrics problem you just created


Go and look at Prometheus. Every `order-platform` target you had green in
[Phase 2](#) is now down, and your Grafana panels are drawing flat lines.

Nothing logged an error. Nothing restarted. `kubectl get pods` says `2/2`.

STRICT mTLS means every connection into a meshed pod must present a client certificate.
Prometheus has no sidecar and no certificate, so its plaintext scrape of `order-api:8000/metrics` is
refused at the proxy — before your application ever sees it. The `ServiceMonitor` you enabled in
[§13.3](#133-confirm-your-app-is-being-scraped) cannot work here, and no
amount of fixing its selectors will help.

**This is the most valuable thing in this phase.** A security control that silently breaks
observability is the ordinary case, not a freak event, and you have just caused one on purpose while
nothing is at stake. In production this arrives as "the dashboard has been flat since Tuesday and
nobody noticed".

The fix is to stop scraping the application and start scraping the **sidecar's merged endpoint**.
`istio-proxy` scrapes your app over loopback *inside* the pod — where there is no mTLS to satisfy —
and re-publishes those metrics combined with Envoy's own. One scrape, both halves, and it survives
STRICT because Prometheus is now talking to a port the sidecar deliberately exposes.

Swap the monitors — off with one, on with the other:

```bash
# deploy/charts/order-platform/values.yaml
serviceMonitor:
  enabled: false     # plaintext; refused by STRICT mTLS from here on
podMonitor:
  enabled: true
  interval: 15s
```

```bash
helm upgrade --install order-platform deploy/charts/order-platform \
  --namespace shop --values deploy/env/local/values.yaml --wait
```

> **Why a `PodMonitor` and not another `ServiceMonitor`.** The merged endpoint lives on the **pod**,
> on the sidecar's own port, and is not fronted by any Service — so a `ServiceMonitor`, which selects
> Services, has nothing to select. That is the whole reason the kind changes.
>
> And it must be addressed by **number**. Istio's docs: *"forwards requests to the sidecar telemetry
> port **15020 for merged metrics** or **15090 for Envoy-only metrics**"*. 15090 is the port carrying
> the name `http-envoy-prom`; **15020 is unnamed in the pod spec**, so `port:` cannot reach it and
> `portNumber: 15020` is required. Pick 15090 by name and you will get `istio_requests_total` — so
> Kiali looks perfectly healthy — while your application's own `orders_received_total` never appears
> again. A half-failure that looks like a success is worse than an outage.

Now confirm you get **both halves** from one scrape:

```bash
kubectl -n monitoring port-forward svc/monitoring-kube-prometheus-prometheus 9090:9090 &

# yours, from §3:
curl -s 'http://localhost:9090/api/v1/query?query=orders_received_total' | jq '.data.result | length'

# Istio's, which you now get for free and Kiali needs:
curl -s 'http://localhost:9090/api/v1/query?query=istio_requests_total' | jq '.data.result | length'
```

Both non-zero once traffic has flowed. If `istio_requests_total` is empty but yours is not, you are
scraping the application port rather than `15020`. If yours is empty but Istio's is not, you are on
`15090`.

> **The trap in this swap:** a pod with no sidecar has no merged endpoint, so the `PodMonitor`
> silently matches nothing and that workload vanishes from Prometheus with no error at all. A
> workload that *leaves* the mesh loses its metrics. That is worth an alert of its own —
> `absent(up{job="order-platform"})` — which is precisely the kind of "the monitoring stopped"
> condition [§13.5](#135-an-alert-that-means-something) argues you should page
> on.

### 9.7 Commit, and a word on what you cannot verify yet


```bash
git add deploy/platform/istio deploy/platform/floci-bootstrap.yaml
git commit -m "feat(platform): istio with strict mtls and default-deny authz"
```

`order-api` and `order-worker` don't exist yet, so §9.4's proof covers Floci only. The rest of the mesh — the ingress path, the authorization policies keyed on those two service accounts — becomes verifiable in [§11](#11-argo-cd-pull-based-delivery), when Argo CD deploys the chart into the now-enrolled `shop` namespace. If a page load returns `RBAC: access denied` at that point, the policy in §9.5 is what to read first, and `istioctl analyze -n shop` is what to run.

When it is running, do not accept a `200` from the browser as proof that the edge is meshed — a `200`
only tells you bytes moved. Ask the destination sidecar which security policy it applied:

```bash
kubectl -n shop exec deploy/order-api -c istio-proxy -- \
  pilot-agent request GET 'stats?filter=istio_requests_total' \
  | grep reporter.destination | grep -o 'connection_security_policy\.[a-z_]*'
# connection_security_policy.mutual_tls
```

`mutual_tls`, with `source_principal` reading
`spiffe://cluster.local/ns/ingress-nginx/sa/ingress-nginx`, is the evidence. `none` or `unknown` means
a working website with no mTLS at the edge, which is what you get without the two Ingress annotations
in §9.4.

### 9.8 Canary: two versions of `pricing` behind one Service


Everything above secures traffic. This section *steers* it — and it is the half of a service mesh that
most people install one for.

> **This section needs a service that does not exist yet.** Traffic shifting requires two versions of
> something, and a synchronous call to shift. [Phase 7](#) builds
> `pricing` — the first service-to-service request path in this platform
> ([§9.1](#91-what-a-mesh-actually-buys-you-here--and-what-it-doesnt) is blunt about there not being
> one until then). **Read this now, run it after [§19](#19-a-third-service-pex-packaging-and-a-dashboard).**
> It lives here because it is mesh material and belongs with the rest of the mesh, not because you can
> execute it in sequence.

The shape: two `Deployment`s, `pricing-v1` and `pricing-v2`, behind **one** `Service` named `pricing`.
The Service selects on `app.kubernetes.io/name: pricing` and matches both. Kubernetes alone would
therefore round-robin across all pods of both versions with no way to control the ratio — replica
counts are the only lever, and they are a coarse and slow one. Istio adds the lever.

**The pod template must carry the version label.** The `DestinationRule` subsets select on pod labels,
not Deployment labels:

```yaml
  template:
    metadata:
      labels:
        app.kubernetes.io/name: pricing
        version: {{ $version }}      # v1 or v2 — the subsets select on THIS
```

Put `version` only on the Deployment and the subsets match nothing. Envoy then has no healthy endpoint
for either subset and every call fails — a total outage produced by a label in the wrong place.

#### The Service port name is what makes any of this work

```yaml
spec:
  selector:
    app.kubernetes.io/name: pricing
  ports:
    - { name: grpc, port: 50051, targetPort: grpc }
    - { name: metrics, port: 9090, targetPort: metrics }
```

**The port must be named `grpc`.** There is no `grpc:` stanza in a `VirtualService` — gRPC rides
HTTP/2 and is routed by the ordinary `http:` block, and what tells Istio to treat this Service's
traffic as HTTP/2 with gRPC semantics is the port name: Istio's protocol selection maps the `grpc` /
`grpc-*` prefix to HTTP/2. Name it anything else and Istio falls back to plain TCP passthrough, where
weights, retries, timeouts and gRPC-status-aware outlier detection — all L7 features — simply do not
apply, while the manifests still apply cleanly and traffic still flows round-robin.

Confirm with `kubectl -n shop get svc pricing -o jsonpath='{.spec.ports[*].name}'`, or
`istioctl analyze -n shop`.

#### `DestinationRule` — subsets, and the pool policy

**`deploy/platform/istio/pricing-traffic.yaml`** (the file itself carries all of the arithmetic below as inline comments; stripped here so the prose can do the work)

```yaml
apiVersion: networking.istio.io/v1
kind: DestinationRule
metadata:
  name: pricing
  namespace: shop
spec:
  host: pricing.shop.svc.cluster.local
  subsets:
    - name: v1
      labels:
        version: v1
    - name: v2
      labels:
        version: v2
  trafficPolicy:
    connectionPool:
      tcp:
        maxConnections: 20
      http:
        http2MaxRequests: 100
        maxRequestsPerConnection: 0
    outlierDetection:
      consecutive5xxErrors: 3
      interval: 15s
      baseEjectionTime: 30s
      maxEjectionPercent: 50
```

A `DestinationRule` names subsets; it does not route to them. Routing is the `VirtualService`, below.
Each subset becomes its own Envoy cluster, and both inherit this `trafficPolicy` because neither
overrides it.

`maxRequestsPerConnection: 0` means unlimited requests per HTTP/2 connection. HTTP/2 is designed for
long-lived multiplexed connections; forcing periodic reconnects adds handshake latency to a service
living inside a 2 second budget, for no gRPC-specific benefit.

**The two outlier-detection defaults that had to change, and why:**

| Field | Istio default | Here | Reason |
|---|---|---|---|
| `consecutive5xxErrors` | 5 | **3** | With 2–3 replicas per subset, one bad pod serves a large share of total volume. Waiting for 5 errors is too much blast radius; 1–2 would trip on ordinary transient errors. |
| `maxEjectionPercent` | 10% | **50%** | **10% of a 2-replica pool rounds down to zero ejectable hosts** — outlier detection would be configured and functionally inert. 50% guarantees room to eject one of two while always leaving one healthy replica standing. |

That second row is the one to remember. **Outlier detection's defaults assume a pool much larger than
a laptop cluster's**, and a percentage that rounds to zero produces a feature that reports as enabled
and never fires. Nothing warns you.

`baseEjectionTime: 30s` stays at the default: long enough that an ejected pod is not reconsidered on
the very next 15 second sweep, short enough that a transient blip self-heals without an operator.

#### `VirtualService` — 90/10, and the arithmetic that produced the retry budget

```yaml
apiVersion: networking.istio.io/v1
kind: VirtualService
metadata:
  name: pricing
  namespace: shop
spec:
  hosts:
    - pricing.shop.svc.cluster.local
  http:
    - route:
        - destination:
            host: pricing.shop.svc.cluster.local
            subset: v1
            port:
              number: 50051
          weight: 90
        - destination:
            host: pricing.shop.svc.cluster.local
            subset: v2
            port:
              number: 50051
          weight: 10
      timeout: 1800ms
      retries:
        attempts: 2
        perTryTimeout: 500ms
        retryOn: cancelled,unavailable,connect-failure,refused-stream
```

Weights are the easy part. **The timeouts are the part worth reading**, and every number below is
derived inward from one fact: `order-api` sets a **2000 ms client-side gRPC deadline** and returns
HTTP 502 with no fallback when it expires
([§19.1](#191-pricing-deliberately-synchronous)).

**1. The route timeout is 1800 ms — deliberately *less* than the client's 2000 ms.**

A route timeout longer than the caller's deadline is pointless: `order-api`'s own timer fires at 2000
ms regardless of what Envoy is still doing, so everything Envoy does past that point is work for a
caller who has already given up. Setting it 200 ms *under* means **Envoy is the one that gives up**,
and it returns a clean `upstream request timeout` to the stub. Set them equal and the two timers race
to fire at the same instant, making the failure mode nondeterministic — sometimes a proxy-side error,
sometimes a bare `DEADLINE_EXCEEDED` from the gRPC library. A failure you cannot reproduce is a
failure you cannot alert on.

**2. The retry envelope must fit inside both ceilings.**

```
  3 attempts (1 initial + 2 retries) × 500 ms perTryTimeout   = 1500 ms
+ 2 backoff gaps × ~25 ms minimum                             =   50 ms
                                                              ─────────
  worst case                                                  ≈ 1550 ms

  1800 ms route timeout    − 1550 ms  =  ~250 ms slack
  2000 ms client deadline  − 1550 ms  =  ~450 ms slack
```

`attempts: 2` in Istio means two *retries*, so three attempts total. Note that Istio applies
exponential backoff between attempts — a detail that is easy to omit from the sum and that is exactly
big enough to matter when the slack is 250 ms.

> **Retries that can outlive the caller's deadline are worse than no retries at all.** They burn the
> time budget on attempts whose results nobody will ever see, while the caller has already returned an
> error. The arithmetic exists so the *full envelope* sits inside both ceilings, not just the outer
> one. If you change `perTryTimeout`, redo the sum — this is the number people bump to "give it a
> chance" and thereby guarantee the timeout they were trying to avoid.

**3. `retryOn` is deliberately narrow.**

Retried:

- `unavailable`, `cancelled` — transient and connection-level, matching Istio's own cluster-wide
  default set. Exactly the class a retry against a *different* pod is likely to fix.
- `connect-failure`, `refused-stream` — HTTP/2-level: TCP connect failed, or the stream was reset
  before headers. The request never reached an application handler, so retrying is safe and cheap.

Deliberately **not** retried:

- `deadline-exceeded` — the request already spent its per-try budget once. Retrying spends more of the
  same 2000 ms on the same failure mode.
- `resource-exhausted`, `internal` — the instance is already overloaded or broken. Retrying hammers a
  struggling pod. **That is outlier detection's job — eject it — not a retry's.**

The general principle: **retry only what a different pod would plausibly answer.** Everything else is
a load amplifier attached to a service that is already failing, which is how a small incident becomes
a large one.

#### Lock the caller down while you are here

`pricing` is called synchronously with no fallback, so its blast radius should be as small as it can
be. Exactly one workload has business calling it:

```yaml
apiVersion: security.istio.io/v1
kind: AuthorizationPolicy
metadata:
  name: allow-order-api-to-pricing
  namespace: shop
spec:
  selector:
    matchLabels:
      app.kubernetes.io/name: pricing
  action: ALLOW
  rules:
    - from:
        - source:
            principals:
              - "cluster.local/ns/shop/sa/order-api"
```

Not `order-worker`, not the frontend, nothing in `floci`. The same policy file also gains
`cluster.local/ns/shop/sa/frontend` on the `order-api` rule, since the dashboard calls the API.

#### Watch it move

```bash
kubectl apply -f deploy/platform/istio/pricing-traffic.yaml
istioctl analyze -n shop

# generate traffic
for i in $(seq 1 200); do
  curl -sS -X POST http://shop.localtest.me/orders \
    -H 'content-type: application/json' \
    -d '{"customer":"ada","sku":"WIDGET-1","quantity":3,"amount_cents":4999}' \
    | jq -r .priced_by
done | sort | uniq -c
```

Roughly 180 `v1` to 20 `v2`. Open `http://app.localtest.me` and the same split draws itself live.

Now shift it. Edit the weights to 50/50, commit, and let Argo CD sync — **the canary is a git
operation**, which is the whole point of [Phase 3](#). The bar moves within a sync
interval, and because v2 discounts 10% at `quantity >= 3` the totals visibly change too. A canary
between two identical builds proves the routing works; a canary between two *different behaviours*
proves you would have noticed if the new one were wrong.

### 9.9 Break it on purpose: fault injection


A canary tells you the routing works. It tells you nothing about what happens when `pricing` is slow —
and slow is the failure mode that matters, because it is the one that consumes the caller's budget
rather than failing fast.

Istio can inject the failure for you, with no change to any application:

**`deploy/platform/istio/pricing-fault-injection.yaml.disabled`** (abridged — the route block is identical to `pricing-traffic.yaml`'s)

```yaml
  http:
    - fault:
        delay:
          percentage:
            value: 50
          fixedDelay: 3s
      route:
        # ... the same 90/10 destinations, timeout and retries as pricing-traffic.yaml
```

**3 seconds is chosen to beat every timer in the chain.** It is longer than the 1800 ms route timeout
and longer than `order-api`'s 2000 ms deadline, so neither can rescue the call. The point of a drill
is a real, visible failure — not a near-miss that leaves you unsure whether anything happened.

> **The `.disabled` suffix is the safety mechanism.** Argo CD's manifest glob does not match it, so
> this file sits in git, reviewed and version-controlled, and is never applied by the reconciler. An
> operator applies it by hand and deletes it by hand. **A chaos experiment that GitOps can apply on
> its own is a chaos experiment that will eventually apply itself on a Friday.**

```bash
kubectl apply -f deploy/platform/istio/pricing-fault-injection.yaml.disabled
```

What to watch, in the order it becomes visible:

| Where | What you should see |
|---|---|
| `order-api` metrics | `pricing_calls_total{result="timeout"}` climbing |
| `order-api` logs | `pricing call failed ... code=DEADLINE_EXCEEDED` |
| `POST /orders` | HTTP **502** on the affected fraction — no fallback, a failed pricing call *is* a failed order |
| the frontend | its error counter climbing in lockstep with the 50% fault rate |
| [[kiali]] | elevated error rate on `pricing`, and pods being **ejected** from the pool |

That last row is the subtle one and the reason this drill is worth running. A client-side injected
delay registers in `order-api`'s **own sidecar** as a gateway timeout against the `pricing` cluster
— so it counts toward `consecutive5xxErrors: 3`, and Envoy starts ejecting pricing pods that are
perfectly healthy. The fault is in the proxy, not the pod, and outlier detection cannot tell the
difference.

**That is not a bug in the drill; it is the lesson.** Outlier detection ejects on *observed symptoms*,
and a symptom seen at the client cannot distinguish "this pod is sick" from "the path to this pod
is sick". In production this is how a network problem turns into a capacity problem: every client
independently decides the backends are bad and ejects them, and a service with no failing pods loses
half its pool.

Revert:

```bash
kubectl delete -f deploy/platform/istio/pricing-fault-injection.yaml.disabled
```

> **Why this ships as a whole copy of the route rather than a patch.** Istio does not allow two
> `VirtualService`s to independently define routes for the same host — behaviour would depend on merge
> order, which is not something to depend on. So the fault manifest reproduces the 90/10 destinations,
> the timeout and the retries verbatim, and applying it *replaces* the canary routing under the same
> resource name. Deleting it hands the host back to `pricing-traffic.yaml` on the next Argo CD sync.
> The duplication is real and is the honest cost of the constraint.

---

## Where you are

Every call between meshed workloads is mutually authenticated and encrypted with certificates you
never issued by hand. `floci` refuses anything that is not `order-api` or `order-worker`, by
identity — not by IP, which can be stolen. Kiali draws the graph, including the refusals.

Your monitoring survived, because you fixed it when it broke.

You have also written the routing, retry and outlier-detection policy for a canary
([§9.8](#98-canary-two-versions-of-pricing-behind-one-service)) and the drill that breaks it
([§9.9](#99-break-it-on-purpose-fault-injection)) — neither of which you can run until
[Phase 7](#) builds the `pricing` service they steer. Come back for them.

**Next: [Phase 5 — Making it someone else's platform](#).**

[← All phases](docs/README.md) · [← Phase 3 — Delivery: git as the deploy button](#) · [Phase 5 — Making it someone else's platform →](#)

## 14. Backstage: paved paths, not documentation


### 14.1 What a portal is actually for


Everything up to here is a platform that one person can operate because that person built it. Hand it to a second engineer and the first question is "how do I add a service?", and the honest answer is currently "read fourteen sections of a tutorial". That answer does not scale, and the usual fix — a wiki page titled *How to add a service* — decays within two sprints because nothing breaks when it goes stale.

A **paved path** is that document made executable. The rule that makes it work:

> **The paved path must be the easiest path.** If the golden path is a form that produces a reviewed PR in ninety seconds, and the alternative is copying another service's directory and guessing, people take the form. If the paved path is slower than copy-paste, you have built a portal nobody uses and a wiki page with better formatting.

We use two parts of Backstage:

- **The catalog** — what exists, who owns it, what it depends on. Entities live in the repo next to the code, so ownership is reviewed like code.
- **The scaffolder** — templates that take a form and produce a change. Ours produce **pull requests against this repo**, never direct pushes to `main`. A paved path that bypasses review is not a path, it's a hole.

Two paved paths, matching the two things people ask for:

| Template | Produces | Reviewed by |
|---|---|---|
| **New service** | `services/<name>/` (code, Dockerfile, tests) + one chart file that deploys it | a PR |
| **New S3 bucket** | `deploy/platform/infra/<name>.yaml`, applied by Argo CD | a PR |

Both work because of decisions made earlier: CI discovers services from the filesystem ([§12.5](#125-the-pipeline)) and Argo CD recurses `deploy/platform` ([§11.4](#114-the-app-of-apps)). Neither template edits a pipeline, and neither touches the cluster.

> **Backstage is a framework, not a product.** You do not install Backstage; you *build* a Backstage. `create-app` scaffolds a TypeScript monorepo that is now your code, and adding a plugin means editing `packages/backend/src/index.ts` and rebuilding an image. That is the deal, and it is why we chose to build our own image rather than run the public demo one — the demo image's plugin set is fixed, and the first thing you'll want is a plugin it doesn't have.

### 14.2 First, an npm proxy in Nexus


A Backstage build pulls several thousand npm packages. Every one of them is a supply-chain event, and [§5.1](#51-what-nexus-is-actually-for) said the whole point of Nexus is that nothing enters this platform unproxied. So npm gets the same treatment PyPI and Go already have:

```bash
curl -u admin:admin123 -X POST 'http://localhost:8081/service/rest/v1/repositories/npm/proxy' \
  -H 'Content-Type: application/json' -d '{
    "name": "npm-proxy",
    "online": true,
    "storage": { "blobStoreName": "default", "strictContentTypeValidation": true },
    "proxy": { "remoteUrl": "https://registry.npmjs.org", "contentMaxAge": 1440, "metadataMaxAge": 1440 },
    "negativeCache": { "enabled": true, "timeToLive": 1440 },
    "httpClient": { "blocked": false, "autoBlock": true },
    "npm": { "removeNonCataloged": false }
  }'

curl -s -u admin:admin123 http://localhost:8081/service/rest/v1/repositories | jq -r '.[].name'
```

### 14.3 Scaffold the portal


Backstage needs an Active LTS Node. Let `create-app` choose the Yarn version:

```bash
brew install node@22
corepack enable

npx @backstage/create-app@latest --path portal
cd portal
```

> **Do not run `yarn set version` here.** `create-app` pins the version it wants in `package.json`'s
> `packageManager` field and Corepack honours it, so a second pin buys nothing and an older one makes
> the scaffold unable to read the `.yarnrc.yml` it just wrote. If you ever need to move it, move it
> **forwards**: `yarn set version stable`.

Two of the settings `create-app` writes into `.yarnrc.yml` are worth knowing rather than deleting:
`npmMinimalAgeGate` refuses packages published less recently than the given window, and
`npmPreapprovedPackages` exempts `@backstage/*` from it. That is
[§5.1](#51-what-nexus-is-actually-for)'s argument applied to time instead of
location — Nexus controls *where* a dependency comes from, the gate controls *how battle-tested* it is
when you take it. `yarn add --no-time-gate` bypasses it for one command when you genuinely need a fresh
release.

Point it at Nexus rather than the public registry — the same choke point the services use:

**`portal/.yarnrc.yml`** (add to what `create-app` generated)

```yaml
npmRegistryServer: "http://nexus:8081/repository/npm-proxy/"
unsafeHttpWhitelist:
  - nexus
```

Add the scaffolder's GitHub actions. In the new backend system every provider's actions ship as their own module and none are on by default:

```bash
yarn --cwd packages/backend add @backstage/plugin-scaffolder-backend-module-github
```

**`portal/packages/backend/src/index.ts`** — add one line next to the other `backend.add(...)` calls:

```typescript
// Without this, `publish:github:pull-request` does not exist and every template
// run fails at the last step with "action not found" — after doing all the work.
backend.add(import('@backstage/plugin-scaffolder-backend-module-github'));
```

Check it boots locally before you think about containers:

```bash
yarn install
yarn start          # http://localhost:3000
```

### 14.4 Configure it for this platform


Replace `<your-github-user>` with the account your fork of this repo lives under, here and everywhere
else it appears in this phase. The URLs are `https`, not `http`: the Backstage frontend calls
`crypto.randomUUID`, which the browser only exposes in a secure context, so the portal is served over
TLS at the edge and every URL it knows about itself has to agree ([§14.8](#148-build-and-deploy-the-portal)).

**`portal/app-config.production.yaml`**

```yaml
app:
  baseUrl: https://backstage.localtest.me

backend:
  baseUrl: https://backstage.localtest.me
  listen:
    # Object form. The string shorthand (`listen: ':7007'`) is rejected:
    #   Invalid type in config for key 'backend.listen', got string, wanted object
    # host must be 0.0.0.0, not the 127.0.0.1 default, or the container binds to
    # loopback and the kubelet's probes never reach it.
    host: 0.0.0.0
    port: 7007
  cors:
    origin: https://backstage.localtest.me
  database:
    client: pg
    connection:
      host: ${POSTGRES_HOST}
      port: ${POSTGRES_PORT}
      user: ${POSTGRES_USER}
      password: ${POSTGRES_PASSWORD}

integrations:
  github:
    - host: github.com
      # Fine-grained PAT, this repository only, Contents + Pull requests: RW.
      token: ${GITHUB_TOKEN}

auth:
  providers:
    guest:
      # Backstage refuses guest sign-in outside development unless you say this
      # out loud. Read the end of §14.8 before you copy this line anywhere real.
      dangerouslyAllowOutsideDevelopment: true

catalog:
  rules:
    - allow: [Component, System, API, Resource, Location, Template, Group, User]
  locations:
    - type: url
      target: https://github.com/<your-github-user>/modern-devops/blob/main/catalog-info.yaml
    - type: url
      target: https://github.com/<your-github-user>/modern-devops/blob/main/deploy/backstage/templates/new-service/template.yaml
      rules: [{ allow: [Template] }]
    - type: url
      target: https://github.com/<your-github-user>/modern-devops/blob/main/deploy/backstage/templates/new-bucket/template.yaml
      rules: [{ allow: [Template] }]
```

> **`catalog.rules` is not boilerplate.** It is the allow-list of entity kinds a location may introduce. Without it, anyone who can open a PR to a catalogued repo can introduce a `Template` — and a Template is code that runs in your scaffolder with your GitHub token. The rules are why a catalog file is safe to accept from a service team and a template file is not.

### 14.5 Catalogue what already exists


The catalog is only as useful as it is complete, and it goes stale the moment it lives somewhere other than the code.

**`catalog-info.yaml`** (repo root)

```yaml
apiVersion: backstage.io/v1alpha1
kind: System
metadata:
  name: order-platform
  description: Order intake and persistence
spec:
  owner: group:default/platform
---
apiVersion: backstage.io/v1alpha1
kind: Component
metadata:
  name: order-api
  description: FastAPI order intake; prices every order over gRPC before accepting it
  annotations:
    github.com/project-slug: <your-github-user>/modern-devops
spec:
  type: service
  lifecycle: production
  owner: group:default/platform
  system: order-platform
  providesApis: [orders]
  consumesApis: [pricing]
  dependsOn: [component:default/pricing]
---
apiVersion: backstage.io/v1alpha1
kind: Component
metadata:
  name: order-worker
  description: Go consumer, writes to S3 and DynamoDB
spec:
  type: service
  lifecycle: production
  owner: group:default/platform
  system: order-platform
  consumesApis: [orders]
  dependsOn: [resource:default/orders-raw]
---
apiVersion: backstage.io/v1alpha1
kind: Component
metadata:
  name: pricing
  description: >-
    gRPC pricing service. Runs as two versions behind one Kubernetes Service so
    Istio can shift traffic between them; the version that answered is returned
    to the caller as `served_by` (§18).
  annotations:
    github.com/project-slug: <your-github-user>/modern-devops
spec:
  type: service
  lifecycle: production
  owner: group:default/platform
  system: order-platform
  providesApis: [pricing]
---
apiVersion: backstage.io/v1alpha1
kind: Component
metadata:
  name: frontend
  description: >-
    Canary Watch — the Vite dashboard that tallies `served_by` across repeated
    orders, so a traffic shift is something you watch rather than something you
    read out of a metric (§19).
  annotations:
    github.com/project-slug: <your-github-user>/modern-devops
spec:
  type: website
  lifecycle: production
  owner: group:default/platform
  system: order-platform
  consumesApis: [orders]
---
apiVersion: backstage.io/v1alpha1
kind: API
metadata:
  name: orders
  description: The REST surface order-api exposes at the edge
spec:
  type: openapi
  lifecycle: production
  owner: group:default/platform
  system: order-platform
  # Generated, never hand-written — `pants run services/order-api:dump-openapi`.
  # A drift test fails the build if this file stops matching the routes, because
  # a stale spec the portal keeps rendering is worse than no spec at all.
  definition:
    $text: ./services/order-api/openapi.json
---
apiVersion: backstage.io/v1alpha1
kind: API
metadata:
  name: pricing
  description: The gRPC contract between order-api and pricing
spec:
  type: grpc
  lifecycle: production
  owner: group:default/platform
  system: order-platform
  # The .proto is the contract itself, and Pants compiles this exact file into
  # both the Python server and the Go stubs (§17.4). There is no second copy to
  # drift from.
  definition:
    $text: ./protos/shop/v1/pricing.proto
---
apiVersion: backstage.io/v1alpha1
kind: Resource
metadata:
  name: orders-raw
  description: S3 bucket holding raw order payloads
spec:
  type: s3-bucket
  owner: group:default/platform
  system: order-platform
---
apiVersion: backstage.io/v1alpha1
kind: Group
metadata:
  name: platform
spec:
  type: team
  children: []
```

> **`definition.$text` points at the generated artefact, never a copy.** The OpenAPI JSON is emitted
> from the routes and the `.proto` *is* the gRPC contract, so what the portal renders cannot drift from
> what the services actually speak. An API entity whose definition is a hand-maintained second copy is
> worse than no API entity at all.

> **`dependsOn: [resource:default/orders-raw]` is the line that earns the catalog its keep.** When someone asks "what breaks if this bucket goes away", the answer is a query, not an archaeology project. Ownership and dependency edges are the only two pieces of catalog metadata that consistently pay for the effort of maintaining them; the rest is decoration until proven otherwise.

### 14.6 Paved path 1 — a new service


The template ships a skeleton and one chart file. Nothing else, because nothing else is needed: CI discovers any `services/*` directory holding both a `BUILD` and a `Dockerfile`, and the chart globs its own `services/*.yaml`.

**`deploy/backstage/templates/new-service/template.yaml`**

```yaml
apiVersion: scaffolder.backstage.io/v1beta3
kind: Template
metadata:
  name: new-service
  title: New service
  description: A Python service on the paved path — CI, image, deploy, metrics, mesh.
spec:
  owner: group:default/platform
  type: service

  parameters:
    - title: About the service
      required: [name, description, owner]
      properties:
        name:
          title: Name
          type: string
          description: Lowercase, hyphenated. Becomes the directory, image and workload name.
          pattern: '^[a-z][a-z0-9-]{2,29}$'
        description:
          title: What does it do?
          type: string
        owner:
          title: Owner
          type: string
          ui:field: OwnerPicker
          ui:options: { catalogFilter: { kind: Group } }
        exposePublicly:
          title: Route it from the ingress?
          type: boolean
          default: false

  steps:
    - id: fetch
      name: Render the skeleton
      action: fetch:template
      input:
        url: ./skeleton
        values:
          name: ${{ parameters.name }}
          description: ${{ parameters.description }}
          owner: ${{ parameters.owner }}
          exposePublicly: ${{ parameters.exposePublicly }}

    - id: pr
      name: Open a pull request
      action: publish:github:pull-request
      input:
        repoUrl: github.com?owner=<your-github-user>&repo=modern-devops
        branchName: paved-path/service-${{ parameters.name }}
        title: "feat(${{ parameters.name }}): new service via the paved path"
        description: |
          Generated by the **New service** template.

          - `services/${{ parameters.name }}/` — app, tests, Dockerfile
          - `deploy/charts/order-platform/services/${{ parameters.name }}.yaml` — how it deploys

          Merging this builds and deploys it. No pipeline or Argo CD changes are needed.

  output:
    links:
      - title: Review the pull request
        url: ${{ steps.pr.output.remoteUrl }}
```

The skeleton is ordinary files with `${{ values.x }}` placeholders. Start with the two that wire a new service into the platform — how it deploys, and who owns it:

**`deploy/backstage/templates/new-service/skeleton/deploy/charts/order-platform/services/${{ values.name }}.yaml`**

```yaml
# One file per scaffolded service. The chart globs this directory, so adding a
# service is a file creation, never an edit — which is what makes it a clean PR.
name: ${{ values.name }}
description: ${{ values.description }}
port: 8000
replicas: 1
ingress:
  enabled: ${{ values.exposePublicly }}
  host: ${{ values.name }}.localtest.me
```

**`deploy/backstage/templates/new-service/skeleton/services/${{ values.name }}/catalog-info.yaml`**

```yaml
apiVersion: backstage.io/v1alpha1
kind: Component
metadata:
  name: ${{ values.name }}
  description: ${{ values.description }}
spec:
  type: service
  lifecycle: experimental
  owner: ${{ values.owner }}
  system: order-platform
```

The rest of the skeleton lives in the repo at `deploy/backstage/templates/new-service/skeleton/services/${{ values.name }}/`:

```
${{ values.name | replace('-', '_') }}/__init__.py   … /main.py   … /settings.py
tests/__init__.py   tests/test_api.py
BUILD               Dockerfile
```

Name the package directory `${{ values.name | replace('-', '_') }}`, not `app`. Every service under the
`services/*` source root that declares a top-level `app` package collides with every other one, so
templating the directory makes each scaffolded package name unique by construction — see
[§17.4](#174-source-roots-and-the-duplicate-module-trap).

**`deploy/backstage/templates/new-service/skeleton/services/${{ values.name }}/BUILD`**

```python
# A scaffolded service is a first-class member of the Pants monorepo. Without
# this file CI would not build it at all — service discovery in
# .buildkite/pipeline.sh keys off services/*/BUILD, and a directory Pants does
# not know about cannot be linted, typechecked, tested or packaged. The failure
# would be silent: the pipeline would simply not mention the new service.
python_sources(
    name="lib",
    sources=["${{ values.name | replace('-', '_') }}/**/*.py"],
)

python_tests(
    name="tests",
    sources=["tests/**/*.py", "!tests/__init__.py"],
    # Explicit because several services could otherwise satisfy this import.
    dependencies=[":lib"],
)

pex_binary(
    name="bin",
    entry_point="${{ values.name | replace('-', '_') }}.main:main",
    dependencies=[":lib"],
    # The cluster runs linux/arm64. Without this, a PEX built on a macOS
    # laptop resolves macOS wheels, passes every check, and dies on import
    # inside the container. See 3rdparty/python/BUILD.
    complete_platforms=["3rdparty/python:linux-platform"],
    # dist/ is the Buildah build context; the Dockerfile COPYs by this name.
    output_path="${{ values.name }}.pex",
)
```

**`deploy/backstage/templates/new-service/skeleton/services/${{ values.name }}/Dockerfile`**

```dockerfile
# syntax=docker/dockerfile:1.7
#
# Build context is `dist/` — the output of `pants package`, not this source
# tree. The PEX already carries the whole dependency closure resolved from
# locks/python-default.lock, so there is nothing for this image to install.
FROM docker.io/library/python:3.13-slim

RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin appuser

WORKDIR /app
COPY --chown=10001:10001 ${{ values.name }}.pex /app/service.pex

# A PEX unpacks its dependency closure on first run, so it needs somewhere
# writable. Under readOnlyRootFilesystem it has nowhere and dies in the PEX
# bootstrap before any application log line appears. The chart mounts an
# emptyDir at /tmp to match.
ENV PEX_ROOT=/tmp/pex \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER 10001
EXPOSE 8000
ENTRYPOINT ["python", "/app/service.pex"]
```

The `Dockerfile` is the same four-line shape order-api's has, deliberately — a paved path that builds differently from the services it was modelled on stops being a paved path the first time someone debugs it. There is no `pyproject.toml` and no per-service lock: dependency resolution is the monorepo's job ([§17](#)), which is also what keeps a scaffolded service resolving through Nexus rather than `pypi.org` without the template having to say so. The Python is order-api with the parts a *new* service doesn't have removed: no Kafka producer, no S3 client, no signing key. What survives is the contract the chart depends on — `/healthz`, `/readyz`, `/metrics` on port 8000 — plus one placeholder route so the service does something observable on day one.

> **The metric prefix is computed in Python, not templated.** Service names are hyphenated (`quotes-api`); Prometheus metric names may not be. So `main.py` does `SERVICE.replace("-", "_")` rather than emitting `quotes-api_requests_total`, which would be rejected at registration. Doing it in code instead of in the scaffolder means a rename can never produce an invalid metric name, and `tests/test_api.py` asserts exactly that.

For the chart to render these files, add one template that reads the directory:

**`deploy/charts/order-platform/templates/scaffolded.yaml`**

```yaml
{{- range $path, $_ := .Files.Glob "services/*.yaml" }}
{{- $svc := $.Files.Get $path | fromYaml }}
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: {{ $svc.name }}
  labels: {{- include "op.labels" (dict "name" $svc.name "root" $) | nindent 4 }}
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ $svc.name }}
  labels: {{- include "op.labels" (dict "name" $svc.name "root" $) | nindent 4 }}
spec:
  replicas: {{ $svc.replicas | default 1 }}
  selector:
    matchLabels:
      app.kubernetes.io/name: {{ $svc.name }}
  template:
    metadata:
      labels: {{- include "op.labels" (dict "name" $svc.name "root" $) | nindent 8 }}
      annotations:
        prometheus.io/scrape: "true"
        prometheus.io/path: "/metrics"
        prometheus.io/port: {{ $svc.port | quote }}
    spec:
      # Kubernetes injects a Docker-link env var per Service in this namespace:
      # ORDER_API_PORT, ORDER_WORKER_PORT, PRICING_PORT, FRONTEND_PORT — each
      # set to "tcp://<clusterIP>:<port>". Any app reading a variable of that
      # name as its own config gets a URL where it expected an integer:
      #   ValueError: invalid literal for int() with base 10: 'tcp://10.96...'
      # Env vars outrank every other config source, so the app cannot win.
      # Service links are a Docker-links relic nothing here uses.
      enableServiceLinks: false
      serviceAccountName: {{ $svc.name }}
      imagePullSecrets:
        - name: {{ $.Values.global.imagePullSecret }}
      securityContext:
        runAsNonRoot: true
        seccompProfile: { type: RuntimeDefault }
      containers:
        - name: {{ $svc.name }}
          # Every scaffolded service is built from the same commit, so they all
          # carry the same tag. CI writes it once, in deploy/env/local/values.yaml.
          image: "{{ $.Values.global.registry }}/shop/{{ $svc.name }}:{{ $.Values.scaffolded.tag }}"
          ports:
            - { name: http, containerPort: {{ $svc.port }} }
          env:
            {{- include "op.commonEnv" $ | nindent 12 }}
          readinessProbe:
            httpGet: { path: /readyz, port: http }
          resources:
            requests: { cpu: 50m, memory: 128Mi }
            limits:   { memory: 256Mi }
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities: { drop: ["ALL"] }
          # A scaffolded service is packaged as a PEX, which unpacks its
          # dependency closure on first run and therefore needs somewhere
          # writable. Under readOnlyRootFilesystem it has nowhere and dies in the
          # PEX bootstrap before any application log line appears:
          #   FileNotFoundError: No usable temporary directory found
          # Same mount order-api and pricing carry, for the same reason.
          volumeMounts:
            - { name: tmp, mountPath: /tmp }
      volumes:
        - { name: tmp, emptyDir: {} }
---
apiVersion: v1
kind: Service
metadata:
  name: {{ $svc.name }}
  labels: {{- include "op.labels" (dict "name" $svc.name "root" $) | nindent 4 }}
spec:
  selector:
    app.kubernetes.io/name: {{ $svc.name }}
  ports:
    - { name: http, port: 80, targetPort: http }
{{- if $svc.ingress.enabled }}
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: {{ $svc.name }}
  annotations:
    # Same pair as order-api and frontend, and for the same reason: the edge is
    # outside the mesh, the backend is inside it under STRICT mTLS. Without
    # these, every scaffolded service comes up healthy and answers the browser
    # with "upstream connect error ... connection termination" — which is the
    # worst possible first experience of a paved path (§14.6), because the
    # service is fine and the template is what's broken.
    nginx.ingress.kubernetes.io/service-upstream: "true"
    nginx.ingress.kubernetes.io/upstream-vhost: "{{ $svc.name }}.{{ $.Release.Namespace }}.svc.cluster.local"
spec:
  ingressClassName: nginx
  rules:
    - host: {{ $svc.ingress.host }}
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: {{ $svc.name }}
                port: { name: http }
{{- end }}
{{- end }}
```

Add the default the template references, in **`deploy/charts/order-platform/values.yaml`**:

```yaml
scaffolded:
  tag: "dev"     # CI overwrites this in the env overlay, same as the other two
```

> **`.Files.Glob` is doing something subtle and worth naming.** A chart normally takes its input from `values.yaml`, which means onboarding a service is an *edit* to a shared file — merge conflicts when two teams onboard the same week, and a diff that reviewers have to read carefully. Reading a directory instead turns onboarding into a file *creation*: conflict-free, trivially reviewable, and trivially revertible. When you design a paved path, bias every step towards adding a file rather than editing one.

> **What this deliberately does not template.** No per-service Kafka topic, no per-service secret, no autoscaling. A paved path earns trust by being narrow and predictable; the moment it grows a checkbox for everything, it becomes a worse version of writing the YAML by hand. Services that need more than the path provides should fall off it deliberately and copy the chart's explicit `order-api.yaml` instead.

### 14.7 Paved path 2 — infrastructure


Same shape, different artifact: a form produces a manifest that Argo CD applies.

**`deploy/backstage/templates/new-bucket/template.yaml`**

```yaml
apiVersion: scaffolder.backstage.io/v1beta3
kind: Template
metadata:
  name: new-bucket
  title: New S3 bucket
  description: An S3 bucket, created by GitOps and owned by a team.
spec:
  owner: group:default/platform
  type: resource

  parameters:
    - title: About the bucket
      required: [bucketName, owner]
      properties:
        bucketName:
          title: Bucket name
          type: string
          pattern: '^[a-z0-9][a-z0-9-]{2,62}$'
        owner:
          title: Owner
          type: string
          ui:field: OwnerPicker
          ui:options: { catalogFilter: { kind: Group } }

  steps:
    - id: fetch
      name: Render the manifest
      action: fetch:template
      input:
        url: ./skeleton
        values:
          bucketName: ${{ parameters.bucketName }}
          owner: ${{ parameters.owner }}

    - id: pr
      name: Open a pull request
      action: publish:github:pull-request
      input:
        repoUrl: github.com?owner=<your-github-user>&repo=modern-devops
        branchName: paved-path/bucket-${{ parameters.bucketName }}
        title: "feat(infra): s3 bucket ${{ parameters.bucketName }}"
        description: |
          Creates the `${{ parameters.bucketName }}` bucket. Argo CD applies it on merge.

  output:
    links:
      - title: Review the pull request
        url: ${{ steps.pr.output.remoteUrl }}
```

**`deploy/backstage/templates/new-bucket/skeleton/deploy/platform/infra/${{ values.bucketName }}.yaml`**

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: create-bucket-${{ values.bucketName }}
  namespace: floci
  annotations:
    # Argo CD re-runs this whenever the manifest changes; the command is
    # idempotent, so a re-run is a no-op rather than an error.
    argocd.argoproj.io/hook: Sync
spec:
  backoffLimit: 6
  ttlSecondsAfterFinished: 600
  template:
    metadata:
      annotations:
        sidecar.istio.io/inject: "false"   # §9.3: Jobs and sidecars don't mix
    spec:
      restartPolicy: OnFailure
      containers:
        - name: awscli
          image: amazon/aws-cli:2.32.9
          env:
            - { name: AWS_ENDPOINT_URL,      value: "http://floci.floci.svc.cluster.local:4566" }
            - { name: AWS_DEFAULT_REGION,    value: "us-east-1" }
            - { name: AWS_ACCESS_KEY_ID,     value: "test" }
            - { name: AWS_SECRET_ACCESS_KEY, value: "test" }
          command: ["/bin/sh", "-c"]
          args:
            - |
              set -eu
              aws s3api create-bucket --bucket ${{ values.bucketName }} 2>/dev/null \
                || echo "bucket already exists"
              aws s3api head-bucket --bucket ${{ values.bucketName }}
              echo "owner: ${{ values.owner }}"
```

> **A Job is not a control loop, and you should feel the difference.** This creates the bucket and stops. It will not notice if someone deletes it, it cannot express "make the bucket look like this", and there is no drift detection — the manifest in git can be a lie ten minutes after it merges. The production answer is a provider that reconciles: **Crossplane** or the **AWS Controllers for Kubernetes**, where an `S3Bucket` custom resource is continuously reconciled against the real thing. That's another operator and another CRD set, which is why it isn't here. If you take one idea from this section into a real platform, take that one: **paved paths should produce declarative resources, not one-shot jobs.**

> **The seam, stated plainly.** The bucket appears in the cluster but not in the catalog. Backstage discovers catalog files from *configured locations*, and a brand-new file in an existing repo is not one until either someone adds a location entry or you enable the GitHub discovery provider (`@backstage/plugin-catalog-backend-module-github`) to scan the repo. Until then, add the `Resource` entity to the root `catalog-info.yaml` by hand in the same PR. We're not pretending otherwise: this is the one place where our paved path still needs a human to do a second thing.

### 14.8 Build and deploy the portal


The portal is built by our own CI, on the same path as everything else — it's just a bigger image. It needs a Dockerfile CI can actually run, and a build step in the generator.

Write `portal/Dockerfile`, Backstage's [multi-stage build](https://backstage.io/docs/deployment/docker#multi-stage-build), and use it for every build of the portal — local and CI alike. `create-app` also generates `packages/backend/Dockerfile`; ignore it. That one is a *host build* that only copies a `dist/` you must have produced beforehand with a local Node toolchain, and our CI build step is a Buildah pod with no Node in it. The multi-stage file compiles the project inside the image, so `buildah bud` against the `portal` directory is self-contained.

**`portal/Dockerfile`**

```dockerfile
# Multi-stage build, from https://backstage.io/docs/deployment/docker#multi-stage-build
#
# This exists alongside packages/backend/Dockerfile, which create-app generates
# and which is a *host build*: it expects `yarn install && yarn tsc &&
# yarn build:backend` to have already produced packages/backend/dist/. That is
# fine on a laptop and impossible in our CI, where the build step is a Buildah
# pod with no Node toolchain. This one builds the project inside the image, so
# `buildah bud` against the portal directory is self-contained.
#
# Slower than a host build. That is the trade for not needing Node in CI.

# Stage 1 - Create yarn install skeleton layer
FROM docker.io/library/node:24-trixie-slim AS packages

WORKDIR /app
COPY backstage.json package.json yarn.lock ./
COPY .yarn ./.yarn
COPY .yarnrc.yml ./

COPY packages packages

# No internal plugins in this portal — portal/plugins/ holds only a README, and
# .dockerignore excludes it, so this COPY matches nothing and fails the build.
# Uncomment it the day you add one.
# COPY plugins plugins

RUN find packages \! -name "package.json" -mindepth 2 -maxdepth 2 -exec rm -rf {} \+

# Stage 2 - Install dependencies and build packages
FROM docker.io/library/node:24-trixie-slim AS build

# Set Python interpreter for `node-gyp` to use
ENV PYTHON=/usr/bin/python3

# Install isolate-vm dependencies, these are needed by the @backstage/plugin-scaffolder-backend.
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && \
    apt-get install -y --no-install-recommends python3 g++ build-essential && \
    rm -rf /var/lib/apt/lists/*

# Install sqlite3 dependencies. You can skip this if you don't use sqlite3 in the image,
# in which case you should also move better-sqlite3 to "devDependencies" in package.json.
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && \
    apt-get install -y --no-install-recommends libsqlite3-dev && \
    rm -rf /var/lib/apt/lists/*

USER node
WORKDIR /app

COPY --from=packages --chown=node:node /app .

# .yarnrc.yml points npmRegistryServer at Nexus, so this resolves through the
# choke point (§5.1) exactly like pip and Go do — the build pod's DNS reaches
# `nexus` the same way every other pod does.
RUN --mount=type=cache,target=/home/node/.cache/yarn,sharing=locked,uid=1000,gid=1000 \
    yarn install --immutable

COPY --chown=node:node . .

RUN yarn tsc
RUN yarn --cwd packages/backend build

RUN mkdir packages/backend/dist/skeleton packages/backend/dist/bundle \
    && tar xzf packages/backend/dist/skeleton.tar.gz -C packages/backend/dist/skeleton \
    && tar xzf packages/backend/dist/bundle.tar.gz -C packages/backend/dist/bundle

# Stage 3 - Build the actual backend image and install production dependencies
FROM docker.io/library/node:24-trixie-slim

# Set Python interpreter for `node-gyp` to use
ENV PYTHON=/usr/bin/python3

# Install isolate-vm dependencies, these are needed by the @backstage/plugin-scaffolder-backend.
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && \
    apt-get install -y --no-install-recommends python3 g++ build-essential && \
    rm -rf /var/lib/apt/lists/*

# Install sqlite3 dependencies. You can skip this if you don't use sqlite3 in the image,
# in which case you should also move better-sqlite3 to "devDependencies" in package.json.
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && \
    apt-get install -y --no-install-recommends libsqlite3-dev && \
    rm -rf /var/lib/apt/lists/*

# From here on we use the least-privileged `node` user to run the backend.
USER node

# This should create the app dir as `node`.
# If it is instead created as `root` then the `tar` command below will
# fail: `can't create directory 'packages/': Permission denied`.
# If this occurs, then ensure BuildKit is enabled (`DOCKER_BUILDKIT=1`)
# so the app dir is correctly created as `node`.
WORKDIR /app

# Copy the install dependencies from the build stage and context
COPY --from=build --chown=node:node /app/.yarn ./.yarn
COPY --from=build --chown=node:node /app/.yarnrc.yml  ./
COPY --from=build --chown=node:node /app/backstage.json ./
COPY --from=build --chown=node:node /app/yarn.lock /app/package.json /app/packages/backend/dist/skeleton/ ./

# Note: The skeleton bundle only includes package.json files -- if your app has
# plugins that define a `bin` export, the bin files need to be copied as well to
# be linked in node_modules/.bin during yarn install.

RUN --mount=type=cache,target=/home/node/.cache/yarn,sharing=locked,uid=1000,gid=1000 \
    yarn workspaces focus --all --production && rm -rf "$(yarn cache clean)"

# Copy the built packages from the build stage
COPY --from=build --chown=node:node /app/packages/backend/dist/bundle/ ./

# Copy any other files that we need at runtime
COPY --chown=node:node app-config*.yaml ./

# This will include the examples, if you don't need these simply remove this line
COPY --chown=node:node examples ./examples

# This switches many Node.js dependencies to production mode.
ENV NODE_ENV=production

# This disables node snapshot for Node 20 to work with the Scaffolder
ENV NODE_OPTIONS="--no-node-snapshot"

CMD ["node", "packages/backend", "--config", "app-config.yaml", "--config", "app-config.production.yaml"]
```

`create-app` also writes a `.dockerignore` tuned for the *host* build, and one line in it is fatal to the multi-stage one:

**`portal/.dockerignore`**

```
.git
.yarn/cache
.yarn/install-state.gz
node_modules
# NOT excluded: portal/Dockerfile is a multi-stage build that compiles from
# source inside the image, so `yarn tsc` needs packages/*/src. create-app writes
# this file for the *host* build, where dist/ is prebuilt and the sources are
# dead weight. Excluding them fails with TS18003 "No inputs were found in config
# file", which names tsconfig.json and never mentions Docker.
# packages/*/src
packages/*/node_modules
plugins
*.local.yaml
```

> **Leave `packages/*/src` commented out.** `create-app` writes that exclusion for a host build, where `dist/` is already compiled; our multi-stage build compiles *from* those sources, and excluding them fails `yarn tsc` with `error TS18003: No inputs were found in config file '/app/tsconfig.json'` — an error that names `tsconfig.json` and never mentions Docker. `plugins` stays excluded, because the `COPY plugins plugins` line is commented out above.

**`.buildkite/pipeline.sh`** — after the services loop, before the deploy step:

```sh
# The portal is not a service and does not fit the services template: a
# different Dockerfile path, a different context, and a build measured in
# double-digit minutes.
cat <<YAML

  - label: ":backstage: build portal ($SHA)"
    key: build-portal
    branches: "main"
    agents: { queue: kubernetes }
    timeout_in_minutes: 45
    plugins:
      - kubernetes:
          podSpec:
            volumes:
              - name: nexus-auth
                secret: { secretName: nexus-push }
            containers:
              - image: quay.io/buildah/stable:v1.40.1
                securityContext:
                  privileged: true
                env:
                  - name: STORAGE_DRIVER
                    value: vfs
                  - name: BUILDAH_FORMAT
                    value: docker
                  - name: REGISTRY_AUTH_FILE
                    value: /auth/config.json
                volumeMounts:
                  - name: nexus-auth
                    mountPath: /auth
                    readOnly: true
                command:
                  - |
                    set -euo pipefail
                    buildah bud \\
                      --tls-verify=false \\
                      --file portal/Dockerfile \\
                      --tag "$REGISTRY/shop/portal:$SHA" \\
                      portal

                    buildah push --tls-verify=false "$REGISTRY/shop/portal:$SHA"
YAML
```

> **Twenty to forty minutes, in a `vfs`-backed privileged pod, on your laptop.** That is the honest cost of building Backstage in-cluster, and `vfs` (which we chose in §12.5 because overlay-in-overlay needs privileges we'd rather not grant) is most of it. `branches: "main"` keeps it off every branch build; while you are iterating on the portal, build the same file on your laptop instead and let CI own it once it's stable:

```bash
docker build -f portal/Dockerfile -t nexus:8082/shop/portal:dev portal
docker push nexus:8082/shop/portal:dev
```

Three stages: a skeleton layer of nothing but `package.json` files so dependency installs cache, a build stage that runs `yarn tsc` and `yarn build`, and a production stage carrying only the bundle and production dependencies. It resolves npm through Nexus because `.yarnrc.yml` is copied in before `yarn install`, so the [§14.2](#142-first-an-npm-proxy-in-nexus) proxy applies to the container build too.

Backstage needs a database and a GitHub token. Without the token the catalog is empty and the scaffolder cannot open a pull request, so do this before the install rather than after.

Create a **fine-grained** personal access token at <https://github.com/settings/personal-access-tokens/new>:

- **Repository access** → *Only select repositories* → your fork of this repo.
- **Permissions** → *Repository permissions* → **Contents: Read-only** (Backstage reads `catalog-info.yaml` and the two template files) and **Pull requests: Read and write** (the scaffolder opens the PRs).

Nothing else. Generate it and copy the `github_pat_…` value — GitHub shows it once.

The token comes into the cluster from OpenBao through ESO, exactly like every other secret ([§7.6](#76-let-kubernetes-pull-from-nexus)). Store it at `shop/backstage` under the key `github_token`, which is what the `ExternalSecret` below reads:

```bash
kubectl create namespace backstage

kubectl -n openbao exec -it openbao-0 -- env BAO_TOKEN=root BAO_ADDR=http://127.0.0.1:8200 \
  bao kv put shop/backstage github_token='github_pat_...'
```

**`deploy/platform/backstage-secrets.yaml`**

```yaml
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: backstage
  namespace: backstage
spec:
  refreshInterval: "1h"
  secretStoreRef:
    name: openbao
    kind: ClusterSecretStore
  target:
    name: backstage
    creationPolicy: Owner
  data:
    - secretKey: GITHUB_TOKEN
      remoteRef: { key: backstage, property: github_token }
---
# The portal is pulled from Nexus like everything else, so the `backstage`
# namespace needs its own pull secret. Secrets do not cross namespaces — §7's
# `nexus-pull` lives in `shop` and is invisible here. Without this the kubelet
# reports `no basic auth credentials`, which reads like a registry problem and
# is really a missing Secret in this namespace.
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: nexus-pull
  namespace: backstage
spec:
  refreshInterval: "1h"
  secretStoreRef:
    name: openbao
    kind: ClusterSecretStore
  target:
    name: nexus-pull
    creationPolicy: Owner
    template:
      type: kubernetes.io/dockerconfigjson
      data:
        .dockerconfigjson: |
          {
            "auths": {
              "nexus:8082": {
                "username": "{{ .username }}",
                "password": "{{ .password }}",
                "auth": "{{ printf "%s:%s" .username .password | b64enc }}"
              }
            }
          }
  data:
    - secretKey: username
      remoteRef: { key: nexus, property: username }
    - secretKey: password
      remoteRef: { key: nexus, property: password }
```

**`infra/backstage-values.yaml`**

```yaml
backstage:
  image:
    registry: nexus:8082
    # Set this to the SHA your CI pushed. Nothing rewrites it for you — see the
    # note below.
    repository: shop/portal
    tag: "dev"
    # Secrets do not cross namespaces: §7's nexus-pull lives in `shop`, so the
    # backstage namespace needs its own (created by backstage-secrets.yaml).
    # Without this the kubelet says `no basic auth credentials`.
    pullSecrets:
      - nexus-pull
  # The chart sets `command: ["node","packages/backend"]` with empty args, which
  # DISCARDS the image's CMD — and the image's CMD is where the --config flags
  # live. Without these, Backstage loads only app-config.yaml, whose database
  # block is `client: better-sqlite3, connection: ':memory:'` for local dev. It
  # then dies trying to load a native sqlite binding that was never compiled,
  # and every plugin fails with "Failed to instantiate service 'core.auth'" —
  # an error that names neither the config nor the database.
  args:
    - "--config"
    - "app-config.yaml"
    - "--config"
    - "app-config.production.yaml"

  extraEnvVarsSecrets:
    - backstage

ingress:
  enabled: true
  className: nginx
  host: backstage.localtest.me

postgresql:
  enabled: true
  auth:
    username: bn_backstage
    password: backstage-change-me
```

> **Do not add `POSTGRES_*` to `extraEnvVars`.** With `postgresql.enabled: true` the chart already
> emits those four variables, and a second copy makes the install fail outright — server-side apply
> treats `env` as a list keyed by `name` and rejects duplicate keys. `extraEnvVars` is for the other
> case: point Backstage at a database you run yourself (`postgresql.enabled: false`) and you set
> `POSTGRES_*` there, because then the chart contributes nothing.

Push first. Backstage reads the catalog and both templates from GitHub over the URLs in
`app-config.production.yaml`, so those files have to be on `main` in your fork before the portal starts
looking for them:

```bash
git add portal catalog-info.yaml deploy/backstage deploy/platform/backstage-secrets.yaml \
        deploy/charts/order-platform infra/backstage-values.yaml .buildkite/pipeline.sh
git commit -m "feat(portal): backstage with service and infrastructure paved paths"
git push
```

Then install:

```bash
helm repo add backstage https://backstage.github.io/charts
helm repo update

kubectl apply -f deploy/platform/backstage-secrets.yaml

helm upgrade --install backstage backstage/backstage \
  --namespace backstage --version 2.10.0 \
  --values infra/backstage-values.yaml --wait
```

ESO refreshes on its own schedule, so restart the portal once to be certain it is running with the token you just stored:

```bash
kubectl -n backstage rollout restart deployment/backstage
kubectl -n backstage rollout status  deployment/backstage
```

Open **<https://backstage.localtest.me>** — `https`, not `http`. The frontend calls `crypto.randomUUID`, which browsers expose only in a secure context, so over plain http the UI loads a blank page and nothing else. The certificate is the ingress controller's self-signed default; accept the warning. Sign in as Guest and you should see the catalogue from §14.5 and both templates under **Create**.

> **The portal is the one thing here still deployed by `helm install` from your laptop** — imperatively, outside GitOps, with a tag you set by hand. That is a deliberate stopping point, not an oversight: making it an Argo CD `Application` and teaching CI to bump its tag is exactly the work of [§11.4](#114-the-app-of-apps) and [§12.5](#125-the-pipeline) applied one more time, and doing it yourself is a better test of whether those two sections landed than reading a third worked example. Note the irony while you're at it — **the tool whose entire job is paving paths for other people is, right now, the least paved thing in the cluster.** That is how platforms usually look.

> **Guest sign-in means there is no such thing as "who did that".** Every scaffolder run, every PR the portal opens, is attributed to the one GitHub token — so the audit trail says "the portal did it" and stops. That is tolerable on a laptop and indefensible anywhere else, because the portal's token is more privileged than any individual's. The production shape is GitHub OAuth for user identity plus the scaffolder acting as a GitHub App, so the PR is opened *on behalf of* the person who filled in the form. Wire that up before a second person uses your portal, not after.

> **The bundled PostgreSQL is a `bitnamilegacy` image, and that's a smell worth tracking.** The chart's default points at Bitnami's legacy registry, which is where images go once they stop being the maintained line. It works, and for a laptop it is fine. For anything durable, run Postgres you actually control — an operator, or a managed database — and set `postgresql.enabled: false` with `POSTGRES_*` pointing at it. **Never let your portal's database be the least-maintained component in your platform**, because when it dies you lose the catalog, and the catalog is what you'd have used to find out what depends on it.

---

## Where you are

Someone who has read none of this can add a service to your platform through a form, get a pull
request they can review, and have it built, deployed, meshed and monitored on merge — because every
one of those decisions was made once, here, by you.

**Next: [Phase 7 — One build system, many languages](#).** Adding a service is now cheap, which is exactly what makes one build tool per language stop scaling.

[← All phases](docs/README.md) · [← Phase 4 — Identity between services](#) · [Phase 7 — One build system, many languages →](#)

## 15. End to end


Everything below exercises the whole platform at once. When a step surprises you, the phase that
built that piece is where to go back to:

| What you're exercising | Built in |
|---|---|
| The request reaching the cluster at all | [Phase 0](#) — kind port mappings + ingress-nginx |
| `order-api` → S3 → Kafka → `order-worker` → DynamoDB | [Phase 1](#) |
| Seeing the order count move | [Phase 2](#) |
| A code change reaching the cluster without you | [Phase 3](#) |
| The call being refused when identity is wrong | [Phase 4](#) |
| Adding a service without editing CI or the chart | [Phase 5](#) |
| One command building three languages, and the canary between two pricing versions | [Phase 7](#) |

### 15.1 Send an order


```bash
curl -sS -X POST http://shop.localtest.me/orders \
  -H 'content-type: application/json' \
  -d '{"customer":"ada","sku":"WIDGET-1","quantity":3,"amount_cents":4999}' | jq .
```

```json
{
  "order_id": "3f2b...",
  "status": "accepted",
  "s3_key": "orders/2026-08-15/3f2b....json",
  "total_amount_cents": 13498,
  "discount_cents": 1499,
  "rule_applied": "bulk-10pct",
  "priced_by": "v2"
}
```

`priced_by` is `pricing`'s own report of which version served the request
([§18.1](#181-the-contract)) — it is what makes the canary visible.

### 15.2 Follow it through every hop


**S3 (Floci)** — from inside the mesh, since §9.4 turned on STRICT mTLS ([§6.4](#64-reaching-floci-from-your-laptop) explains why `port-forward` no longer works):

```bash
AWSCLI="kubectl -n floci run awscli-$RANDOM --rm -i --restart=Never \
  --image=amazon/aws-cli:2.32.9 \
  --env AWS_ENDPOINT_URL=http://floci.floci.svc.cluster.local:4566 \
  --env AWS_DEFAULT_REGION=us-east-1 \
  --env AWS_ACCESS_KEY_ID=test --env AWS_SECRET_ACCESS_KEY=test --"

$AWSCLI s3 ls s3://orders-raw/orders/ --recursive
```

**Kafka:**

```bash
kubectl -n kafka run peek -ti --rm --restart=Never \
  --image=quay.io/strimzi/kafka:0.50.1-kafka-4.1.0 -- \
  bin/kafka-console-consumer.sh \
    --bootstrap-server orders-kafka-bootstrap:9092 \
    --topic orders --from-beginning --max-messages 5
```

**DynamoDB (Floci):**

```bash
$AWSCLI dynamodb scan --table-name orders --max-items 5 | jq '.Items'
```

**Logs:**

```bash
kubectl -n shop logs -l app.kubernetes.io/name=order-worker --tail=20
# {"time":"...","level":"INFO","msg":"persisted order","order_id":"3f2b...","offset":0}
```

**Grafana:** <http://grafana.localtest.me> → Dashboards → Order Platform. Generate load and watch it move:

```bash
for i in $(seq 1 200); do
  curl -sS -o /dev/null -X POST http://shop.localtest.me/orders \
    -H 'content-type: application/json' \
    -d "{\"customer\":\"load-$i\",\"sku\":\"WIDGET-1\",\"quantity\":1,\"amount_cents\":100}"
done
```

"Orders accepted /sec" and "Orders persisted /sec" should track each other, and "Unprocessed" should hover near zero.

### 15.3 Ship a change through the whole pipeline


The point of all this is that a code change reaches production without you touching the cluster.

Add a field to the response. In `services/order-api/order_api/main.py`, the `create_order` handler
ends with a `return` dict — add one line to it:

```python
    return {
        "order_id": order_id,
        "status": "accepted",
        "s3_key": key,
        "version": settings.service_version,     # <- add this
        "total_amount_cents": pricing.total_amount_cents,
        "discount_cents": pricing.discount_cents,
        "rule_applied": pricing.rule_applied,
        "priced_by": pricing.served_by,
    }
```

The spec is derived from the route signatures, so regenerate it in the same commit or
`tests/test_openapi_spec.py` fails the build ([§19.6](#196-two-checks-nothing-else-would-catch)):

```bash
pants run services/order-api:dump-openapi > services/order-api/openapi.json

git add services/order-api/order_api/main.py services/order-api/openapi.json
git commit -m "feat(order-api): return service version in the order response"
git push
```

Now watch, in order:

1. **Buildkite** — the pipeline starts within seconds (GitHub webhook). One `lint · typecheck · test · package` step for every language ([§19.5](#195-one-ci-step-instead-of-two)), then the Buildah builds in parallel, then the tag bump.
2. **Nexus** — <http://localhost:8081> → Browse → `docker-hosted`. A new tag appears, named for your commit SHA.
3. **GitHub** — a `chore(deploy): order-platform <sha> [skip ci]` commit lands on `main`.
4. **Argo CD** — <http://argocd.localtest.me>. `order-platform` goes `OutOfSync` → `Syncing` → `Healthy`.
5. **Kubernetes** — a rolling update, with no capacity dip:
   ```bash
   kubectl -n shop rollout status deployment/order-api
   ```
6. **The change is live:**
   ```bash
   curl -sS -X POST http://shop.localtest.me/orders \
     -H 'content-type: application/json' \
     -d '{"customer":"ada","sku":"WIDGET-1","quantity":1,"amount_cents":100}' | jq .version
   ```
   It prints your commit SHA — the image tag, the git commit, and the running version are the same string. **That property is the whole point of the tutorial.**

### 15.4 Break it on purpose


You don't understand a system until you've watched it fail. Do all six.

**① A failing test must block the deploy.**

```bash
cat >> services/order-worker/main_test.go <<'EOF'

func TestDeliberatelyBroken(t *testing.T) {
	t.Fatal("this should stop the pipeline before anything is built")
}
EOF
git commit -am "test: deliberately failing test" && git push
```

Buildkite goes red at `test order-worker`. Because the build steps sit behind a `wait`, **no image is built and no deploy commit is made**. The cluster is untouched. Revert:

```bash
git revert --no-edit HEAD && git push
```

**② Argo CD reverts manual drift.**

```bash
kubectl -n shop scale deployment/order-api --replicas=5
kubectl -n shop get deploy order-api -w    # watch it snap back to 2
```

`selfHeal: true` reconciles it away within ~20 seconds. Argo CD logs the correction. This is what "git is the source of truth" actually means operationally, and it's why the escape hatch in [§11.4](#114-the-app-of-apps) matters during incidents.

**③ Rollback is a git operation.**

```bash
git log --oneline -- deploy/env/local/values.yaml | head -5
git revert --no-edit <the-deploy-commit-sha>
git push
argocd app sync order-platform
```

The previous image tag returns. No registry surgery, no `kubectl set image`, and the audit trail records *who* rolled back and *when*. Alternatively `argocd app rollback order-platform <history-id>` — faster in an incident, but it puts the cluster out of sync with git until you follow up with the revert commit. **Know which one you're doing.**

**④ Kafka survives a broker loss.**

```bash
kubectl -n kafka delete pod orders-broker-0 --wait=false
# keep traffic flowing while it dies
for i in $(seq 1 50); do
  curl -sS -o /dev/null -X POST http://shop.localtest.me/orders \
    -H 'content-type: application/json' \
    -d '{"customer":"chaos","sku":"W","quantity":1,"amount_cents":1}'
  sleep 0.2
done
$AWSCLI dynamodb scan --table-name orders --select COUNT | jq .Count
```

With `replicas: 3` and `min.insync.replicas: 2`, writes continue. Strimzi recreates the broker and it rejoins the ISR. Now try it with two brokers down — `acks=all` writes start failing and order-api returns 502. **That's the system working as designed**: refusing writes it cannot guarantee, rather than accepting them and losing them.

**⑤ Secret rotation.**

```bash
BAO="kubectl -n openbao exec -i openbao-0 -- env BAO_TOKEN=root BAO_ADDR=http://127.0.0.1:8200 bao"
$BAO kv put shop/order-api signing_key="$(openssl rand -hex 32)"

# ESO refreshes within 1m (§7.6)
sleep 70
kubectl -n shop get secret order-api-secrets -o jsonpath='{.data.ORDER_SIGNING_KEY}' | base64 -d | head -c 16; echo

# The running pods still hold the OLD value - env vars are set at container start.
kubectl -n shop rollout restart deployment/order-api
```

That gap between "the Secret changed" and "the pod uses it" is the thing people get wrong in production. Measure your real rotation window, don't assume it.

**⑥ Break the mesh policy.** Add an identity that isn't allowed and watch it get refused at the proxy rather than in your code:

```bash
kubectl -n shop run rogue --rm -it --restart=Never --image=curlimages/curl:8.11.1 -- \
  curl -sS --max-time 5 http://floci.floci.svc.cluster.local:4566/_localstack/health
# RBAC: access denied
```

That pod is in the mesh, holds a valid certificate, and is still refused — because its identity is `sa/default`, not one of the two principals in [§9.5](#95-authorization-deny-by-default-then-allow-the-paths-that-exist). Compare with a stolen-IP attack: there is nothing to steal. Then look at the same request in Kiali's graph as a red edge into `floci`, which is how you'd find it if you weren't the one who caused it.

### 15.5 Onboard a service through the paved path


The closing act, and the only one that tests the platform as a *product* rather than as a system: add a service without touching CI, Argo CD, or the chart.

1. Open <http://backstage.localtest.me> → **Create** → **New service**.
2. Name it `quotes-api`, own it with `platform`, tick **Route it from the ingress**.
3. Follow the link to the pull request. Read the diff — it should be exactly two things: a service directory, and one file under `deploy/charts/order-platform/services/`.
4. Merge it.

Then watch it happen, without doing anything else:

```bash
# CI discovered it because services/quotes-api/ has both a BUILD file and a
# Dockerfile (§19.5). Watch the build list gain a step:
BUILDKITE_COMMIT="$(git rev-parse origin/main)" .buildkite/pipeline.sh | grep 'build quotes-api'

# Argo CD renders it because the chart globs services/*.yaml (§14.6):
argocd app sync order-platform
kubectl -n shop get pods -l app.kubernetes.io/name=quotes-api

# It has a sidecar, because the namespace is enrolled (§9.3):
kubectl -n shop get pod -l app.kubernetes.io/name=quotes-api \
  -o jsonpath='{.items[0].spec.containers[*].name}'; echo
# quotes-api istio-proxy

curl -s http://quotes-api.localtest.me/healthz
```

**Count what you did not do.** You did not edit a pipeline, write a Deployment, register a Prometheus target, request a certificate, or ask anyone for access. Every one of those is a decision the platform already made, encoded once, in a template that is reviewed like code. That is the entire argument for building this thing: not that it makes the first service easy, but that it makes the fiftieth service identical to the first.

**And count what still needs a human.** The PR needs a reviewer. The new service has no Kafka topic, no secret, no dashboard of its own, and its `catalog-info.yaml` only reaches Backstage once the root catalog file references it ([§14.7](#147-paved-path-2--infrastructure)). A paved path is a floor, not a ceiling — the moment you pretend it's a ceiling, teams route around it and you're back to copy-paste with extra steps.

---

## 16. Teardown


**Stop, keep everything:**

```bash
docker stop nexus
kind delete cluster --name devops   # the cluster is disposable; recreate from §4
```

**Remove the mesh but keep the cluster** — worth knowing separately, because unlabelling is not enough:

```bash
kubectl label namespace shop floci ingress-nginx istio-injection-
kubectl -n shop rollout restart deploy         # pods keep their sidecars until recreated
kubectl -n floci rollout restart deploy
kubectl -n ingress-nginx rollout restart deployment/ingress-nginx-controller

helm uninstall kiali-server -n istio-system
helm uninstall istiod -n istio-system
helm uninstall istio-base -n istio-system
```

Do it in that order and mind the middle step: removing the label stops *future* injection and does nothing to running pods. Uninstall `istiod` while sidecars are still running and those pods lose their config source — they keep serving on last-known state until something restarts them, and then they fail closed. **Drain the data plane before you remove the control plane**, always, including during upgrades.

**Full cleanup:**

```bash
kind delete cluster --name devops
docker rm -f nexus
docker volume rm nexus-data
docker rmi $(docker images 'nexus:8082/*' -q) 2>/dev/null || true

# undo the host changes
sudo sed -i.bak '/^127\.0\.0\.1 nexus$/d' /etc/hosts
# then remove "nexus:8082" from insecure-registries in Docker's daemon config
```

Also delete the Buildkite pipeline and agent token in the Buildkite UI, and revoke **both** GitHub PATs — the one Buildkite uses and the one Backstage uses — at <https://github.com/settings/tokens>. **Revoking credentials is part of teardown, not an afterthought** — an abandoned write-capable PAT is exactly how lab environments become incidents, and the portal's token can open pull requests.

---

## Where you are

Done — and more usefully, done *and broken and recovered*, six different ways.

If you want to keep going, [Appendix C](docs/appendices.md#appendix-c--what-this-deliberately-left-out) is
the honest list of what this platform does not do, roughly in the order the omissions will start to
hurt.

[← All phases](docs/README.md) · [← Phase 7 — One build system, many languages](#) · [Appendices →](docs/appendices.md)

## 17. Pants: one build system for four languages


### 17.1 The problem with a build tool per language


The honest case against doing this at all, first. A monorepo build system is a large, opinionated
dependency that every developer must install and every CI job must bootstrap. If you have one service
in one language, it is pure overhead and `uv` is a better answer. **Do not adopt this because it is
sophisticated.** Adopt it when you can name the specific thing it fixes.

Here there are three, and they are all consequences of earlier phases:

| Problem | Created by | What Pants does about it |
|---|---|---|
| One CI step per language, hand-edited per service | [§12.5](#125-the-pipeline) | One `pants lint check test ::` that discovers targets |
| No shared contract between `order-api` and `order-worker` | [§3](#3-the-applications) | One `.proto` generating both languages, checked together |
| Image builds that resolve dependencies inside a privileged Buildah pod | [§12.5](#125-the-pipeline) | Artifacts built once upstream; the image is `FROM` plus `COPY` |

The third is a security argument, not an ergonomics one. A Buildah pod runs `privileged: true`
([§12.5](#125-the-pipeline)); the less that pod does, the better. Today it resolves
a dependency tree from a network index. After this phase it copies a file.

> **Why Pants and not Bazel.** Bazel is the better-known answer and the more powerful one. It is also
> a build system you write build files for, in a language of its own, for every target — and for a
> Python service that means `rules_python`, a `pip_parse` repository rule, and a `py_binary` per
> entry point, all written by hand. Pants infers dependencies from **imports**: it reads the source,
> resolves `from shop.v1 import pricing_pb2` to the target that generates it, and builds the graph
> without being told. That is why the `BUILD` files in this repo are eight lines rather than eighty.
> The cost is that inference is a heuristic and occasionally wrong, which is what
> [§17.4](#174-source-roots-and-the-duplicate-module-trap) is about. For a small polyglot repo the
> trade is clearly worth it; at Google's scale it clearly is not.

### 17.2 Backend maturity, stated up front rather than discovered later


Pants ships language support as backends. Not all of them are stable, and you should know which
before you build a platform on them:

| Backend | Status | Used for |
|---|---|---|
| `pants.backend.python` | stable | `order-api`, `pricing` |
| `pants.backend.python.typecheck.mypy` | stable | typechecking |
| `pants.backend.codegen.protobuf.python` | stable | Python gRPC stubs |
| `pants.backend.experimental.python.lint.ruff.check` / `.format` | **experimental** | linting and formatting |
| `pants.backend.experimental.go` | **experimental** | `order-worker` |
| `pants.backend.experimental.codegen.protobuf.go` | **experimental** | Go gRPC stubs |
| `pants.backend.experimental.javascript` | **experimental** | the frontend's npm install |
| `pants.backend.experimental.typescript` | **experimental** | the frontend's sources |

Five of the eight are experimental in Pants 2.33.0. That is a real risk and it is taken
knowingly: the entire value of a polyglot monorepo is that one tool builds everything, so refusing the
experimental backends means not doing this at all. The mitigation is that **every one of them has a
one-command escape hatch** — `go build`, `npm run build`, `ruff check` — because Pants delegates to
the language's own toolchain rather than reimplementing it. If a backend breaks on upgrade, you lose
orchestration, not the ability to ship.

### 17.3 `pants.toml`


Pants 2.x is **not** on PyPI. It ships as `scie-pants`, a self-bootstrapping launcher binary that
reads `pants_version` out of `pants.toml` and fetches the matching Pants itself. Install the launcher
from its GitHub release, checksum-verified:

```bash
curl -fsSL -o /usr/local/bin/pants \
  https://github.com/pantsbuild/scie-pants/releases/download/v0.13.2/scie-pants-macos-aarch64
echo "a6f3231413ca1f793caffa621171a4b1a0158e7488cd0b5bb3e742cb99cc72a8  /usr/local/bin/pants" \
  | shasum -a 256 -c -
chmod 755 /usr/local/bin/pants
```

> **This one binary comes from outside the choke point, deliberately and once.** Everything Pants
> then resolves — Python wheels, Go modules — goes through [[sonatype-nexus]]
> ([§5.1](#51-what-nexus-is-actually-for)), and CI does not repeat this
> download at all: `.buildkite/pants-ci.Dockerfile` bakes the same checksum-verified launcher into an
> image that lives in Nexus ([§19.5](#195-one-ci-step-instead-of-two)). A pinned, hashed, one-time
> fetch is an honest compromise; `curl … | bash` on every build is not.

The configuration, comments stripped:

```toml
[GLOBAL]
pants_version = "2.33.0"

backend_packages = [
  "pants.backend.python",
  "pants.backend.experimental.python.lint.ruff.check",
  "pants.backend.experimental.python.lint.ruff.format",
  "pants.backend.python.typecheck.mypy",
  "pants.backend.codegen.protobuf.python",
  "pants.backend.experimental.go",
  "pants.backend.experimental.codegen.protobuf.go",
  "pants.backend.experimental.javascript",
  "pants.backend.experimental.typescript",
]

pants_ignore.add = [
  "/deploy/backstage/templates",
  "/portal",
  "/wiki",
  "/raw",
  "/docs",
]

[source]
root_patterns = ["/", "/services/*", "/protos"]

[python]
interpreter_constraints = [">=3.13,<3.14"]
enable_resolves = true
default_resolve = "python-default"

[python.resolves]
python-default = "locks/python-default.lock"

[python-bootstrap]
search_path = ["<PYENV>", "<PATH>", "/opt/homebrew/opt/python@3.13/libexec/bin"]

[python-repos]
indexes = ["http://nexus:8081/repository/pypi-proxy/simple"]

[golang]
cgo_enabled = false
subprocess_env_vars = [
  "GOPROXY=http://nexus:8081/repository/go-proxy",
  "GOSUMDB=off",
  "GOFLAGS=-mod=mod",
  "HOME",
  "PATH",
]

[python-protobuf]
generate_type_stubs = true

[mypy]
install_from_resolve = "python-default"

[test]
timeout_default = 60

[anonymous-telemetry]
enabled = false
```

The non-obvious lines:

- **Ruff's backend path is `pants.backend.experimental.python.lint.ruff.check` / `.format`.** In 2.33
  there is no non-experimental ruff backend to point at.
- **`[mypy] install_from_resolve` but no `[ruff]` equivalent.** mypy is a resolved Python package and
  belongs in the lockfile; ruff is a downloaded binary and does not.
- **`pants_ignore` excludes `/deploy/backstage/templates` and `/portal`.** The scaffolder skeleton's
  `BUILD` file contains nunjucks placeholders and is not valid Python until Backstage renders it;
  Backstage's own Yarn workspace is not ours to build
  ([§14.8](#148-build-and-deploy-the-portal)).
- **`[python-bootstrap] search_path` names the Homebrew path explicitly.** `brew install python@3.13`
  puts the unversioned `python` in `libexec/bin`, which is deliberately off `PATH`, and Pants' default
  search will not find it. `<PYENV>` and `<PATH>` are the defaults and must be repeated, not replaced.
- **`[python-repos]` and `[golang]` both point at Nexus**, for the same reason `uv` did
  ([§5.1](#51-what-nexus-is-actually-for)). `GOSUMDB=off`
  because the public checksum database is unreachable through a private proxy — the same trade, and
  the same caveat, as [§12.5](#125-the-pipeline).
- **`[golang] cgo_enabled = false` is mandatory.** Pants defaults it to *true*, which links
  `order-worker` dynamically against libc. `gcr.io/distroless/static-debian12` has neither libc nor a
  dynamic loader, so the pod dies with `exec /order-worker: no such file or directory` on a file that
  is present and executable.
- **`enable_resolves` with a single named lockfile** means every Python target in the repo resolves
  against `locks/python-default.lock`. One lock, one resolution, no chance of two services
  disagreeing about `protobuf`. Pants still computes per-target dependencies from imports, so a
  service ships only what it imports — one requirements file does not mean one fat artifact.
- **`generate_type_stubs`** is [§18.3](#183-why-protoc-must-emit-pyi-stubs).

Generate the lockfile and commit it:

```bash
pants generate-lockfiles --resolve=python-default
git add locks/python-default.lock 3rdparty/python
```

### 17.4 Source roots, and the duplicate-module trap


`root_patterns = ["/", "/services/*", "/protos"]` declares the import roots. `/services/*` means
each service directory is its own root, so `services/order-api/order_api/main.py` is importable as
`order_api.main`. `/protos` means generated code is importable as `shop.v1.pricing_pb2` rather than by
a path that leaks the directory layout.

That second root is worth doing deliberately. Without it, both services would import their shared
contract by a path — and a path is a thing that changes when someone reorganises a directory.

One rule follows from that layout, and it is not optional: **every service needs a unique top-level
package name.** A shared `/services/*` source root puts them all in the same module namespace, so two
services shipping their code in `app/` — the FastAPI tutorial convention — become the same module
`app`. mypy does not degrade there, it refuses to run at all (`Duplicate module named "app"`), and
Pants cannot infer intra-service imports either, because `from app.settings import settings` is
genuinely ambiguous.

So the packages are named for their services:

```
services/order-api/order_api/     # main.py, settings.py
services/pricing/pricing/         # main.py
```

Underscores, not hyphens: service names are hyphenated and Python packages may not be. The Backstage
skeleton ([§14.6](#146-paved-path-1--a-new-service)) templates its package
directory as `${{ values.name | replace('-', '_') }}` for exactly this reason, so a scaffolded
`quotes-api` arrives with a `quotes_api/` package and collides with nothing.

### 17.5 One command, and what it actually does


```bash
pants lint check test ::
```

`::` means "every target in the repo". One invocation runs ruff over Python, `go vet` over Go, mypy
over both Python services *including the generated protobuf stubs*, and every test suite in the repo.
Adding a fourth language is a line in `backend_packages`, not a new CI step.

```bash
pants list ::                    # every target Pants knows about
pants dependencies --transitive services/order-api:bin
pants package services/pricing:bin
```

`pants dependencies` is the one to reach for when something behaves as if a file is missing: it prints
the graph Pants actually built, which is the graph that matters, rather than the one you assumed from
reading imports.

---

## 18. One `.proto`, two languages


### 18.1 The contract


**`protos/shop/v1/pricing.proto`** (comments stripped — the file itself carries the reasoning inline)

```protobuf
syntax = "proto3";

package shop.v1;

option go_package = "github.com/andytavares/modern-devops/protos/shop/v1;shopv1";

service Pricing {
  rpc PriceOrder(PriceOrderRequest) returns (PriceOrderResponse);
}

message PriceOrderRequest {
  string sku = 1;
  int32 quantity = 2;
  int32 unit_amount_cents = 3;
  string customer = 4;
}

message PriceOrderResponse {
  int32 total_amount_cents = 1;
  int32 discount_cents = 2;
  string rule_applied = 3;
  string served_by = 4;
}
```

`served_by` is the field the rest of this platform is built around: the pricing implementation writes
its own version into it, `order-api` passes it through, and the frontend
([§19.4](#194-the-frontend-vite-and-a-live-tally)) tallies it. That is what makes an Istio weight
change something you watch in a browser rather than infer from a metric.

Money is `int32` cents throughout. Floating-point currency is a bug you ship once.

**`protos/shop/v1/BUILD`** (comments stripped)

```python
protobuf_sources(
    name="protos",
    sources=["*.proto"],
    grpc=True,
)
```

`grpc=True` is not optional decoration — without it protoc emits message classes only, and the
`Pricing` service stub you actually need never appears. **One target feeds both language backends.**

### 18.2 Generate, and look at what came out


```bash
pants export-codegen protos/shop/v1:protos
```

```
protos/shop/v1/pricing.pb.go          Go messages
protos/shop/v1/pricing_grpc.pb.go     Go service stubs
protos/shop/v1/pricing_pb2.py         Python messages
protos/shop/v1/pricing_pb2_grpc.py    Python service stubs
```

You do not commit these and you do not usually run this command — `pants check`, `test` and `package`
generate into a sandbox on demand. `export-codegen` exists so you can *read* the output, and reading
it once is worth the minute.

Now the demonstration that justifies the whole phase. Rename `quantity` to `qty` in the `.proto` and
run:

```bash
pants check ::
```

Python fails on the attribute and Go fails to compile, in the same command, in about ten seconds. The
previous arrangement — a JSON shape agreed in review — surfaced the same mistake as a decode error in
a consumer, after the message was already durable in Kafka.

> **This is the entire argument for a monorepo**, and it is worth being precise about what the
> argument is *not*. It is not "one repo is tidier". It is that a shared interface can be **checked by
> a compiler across language boundaries**, and that check is only possible when one build system sees
> both sides. Split the repo and you are back to versioned artifacts, publish ordering, and a window
> during which the two sides disagree.

### 18.3 Why protoc must emit `.pyi` stubs


```toml
[python-protobuf]
generate_type_stubs = true
```

Generated Python protobuf modules do not define their message classes in the way a reader expects.
`pricing_pb2.py` calls `_builder.BuildTopDescriptorsAndMessages(...)` and the classes appear in
`globals()` **at import time**. mypy reads the file statically, finds no `class PriceOrderRequest`,
and reports:

```
"PriceOrderRequest" is not defined
```

mypy is correct. The class genuinely does not exist statically. `generate_type_stubs = true` has
protoc emit a `.pyi` next to each `_pb2.py` describing what will exist at runtime, and the error
disappears. Pants' own help prefers this to the older mypy-plugin option.

One more, in the same family: `grpcio` ships **no `py.typed` marker**, so mypy cannot see its types at
all regardless of stubs. `types-grpcio` in `3rdparty/python/requirements.txt` is the fix, and mypy's
own suggestion to install it is right. Verified by checking `pants export --resolve=python-default`
for a `py.typed` under `grpc/` — there isn't one.

---

## 19. A third service, PEX packaging, and a dashboard


### 19.1 `pricing`, deliberately synchronous


`services/pricing` serves `shop.v1.Pricing/PriceOrder` on port 50051, plus a small stdlib HTTP server
on 9090 for `/healthz`, `/readyz` and `/metrics` — Kubernetes probes and Prometheus both want HTTP,
and gRPC health checking is a bigger dependency than this needs.

Its behaviour is switched by `PRICING_VERSION` and echoed back in `served_by`:

- **v1** — list price. `total = unit_amount_cents × quantity`, no discount.
- **v2** — the same, except a line with `quantity >= 3` gets 10% off, integer math, rounded down.

That difference is chosen so an Istio weight change is *observable*. Two versions that behave
identically make a canary a matter of faith.

`order-api` calls it on the order path with a **2 second deadline**, using `grpc.aio` so a slow
pricing service cannot block the event loop. On timeout or `UNAVAILABLE` it returns **HTTP 502** and
increments `pricing_calls_total{result,served_by}`.

> **It does not fall back to a locally computed price, and that is a deliberate choice you should
> argue with.** A fallback is the kinder production design: the customer gets an order instead of an
> error. It is also the thing that would make every experiment in
> [§9.8](#98-canary-two-versions-of-pricing-behind-one-service) invisible — a
> canary you cannot see fail teaches nothing, and a silent fallback is how a dependency stays broken
> for a week. **The general rule: a fallback that is not itself alarmed on is a way of not finding
> out.** If you add one, add `pricing_calls_total{result="fallback"}` and an alert on it in the same
> commit.

Synchronous pricing also gives [Phase 4](#) something it did not have. Until
now, `order-api` and `order-worker` were joined by Kafka and never called each other
([§9.1](#91-what-a-mesh-actually-buys-you-here--and-what-it-doesnt) is blunt
about the mesh having no request path to secure between them). `pricing` is the first synchronous
service-to-service hop in this platform, which is what makes retries, timeouts, traffic shifting and
outlier detection mean anything at all.

#### Wiring `order-api` to it

A pricing service nothing calls is a pricing service you cannot canary. The rest of this section is
the caller side: the address, the client, the metric, the call, and the tests. Do it now — everything
downstream ([§19.4](#194-the-frontend-vite-and-a-live-tally),
[§9.8](#98-canary-two-versions-of-pricing-behind-one-service)) depends on it.

**Address and deadline.** Two settings, appended to `Settings.__init__`:

**`services/order-api/order_api/settings.py`**

```python
        self.pricing_addr = os.getenv(
            "PRICING_ADDR", "pricing.shop.svc.cluster.local:50051"
        )
        self.pricing_timeout_seconds = float(
            os.getenv("PRICING_TIMEOUT_SECONDS", "2.0")
        )
```

The default matches the `Service` the chart creates in [§19.3](#193-a-pex-needs-somewhere-to-write-and-readonlyrootfilesystem-gives-it-nowhere)
(`pricing`, namespace `shop`, port 50051), so `order-api.yaml` needs no new env entry. The timeout is
a setting rather than a constant because it is the number you tune when
[§9.8](#98-canary-two-versions-of-pricing-behind-one-service) starts injecting
delays.

**The client.** Add the imports and the metric to `main.py`:

**`services/order-api/order_api/main.py`**

```python
import grpc

from shop.v1 import pricing_pb2, pricing_pb2_grpc
```

```python
PRICING_CALLS = Counter(
    "pricing_calls_total",
    "Outcomes of calls to the pricing service",
    ["result", "served_by"],
)
```

`served_by` as a metric label is safe here only because its cardinality is bounded by the number of
deployed pricing versions. Do not label metrics with anything a caller controls.

```python
class PricingClient:
    """Thin async wrapper around the generated Pricing stub.

    Uses grpc.aio so a slow or unavailable pricing service can't block the
    event loop. Deliberately has no fallback path: a failed price is a failed
    order, not a locally guessed one.
    """

    def __init__(self, address: str, timeout_seconds: float) -> None:
        self._channel = grpc.aio.insecure_channel(address)
        self._stub = pricing_pb2_grpc.PricingStub(self._channel)
        self._timeout_seconds = timeout_seconds

    async def price_order(
        self, *, sku: str, quantity: int, unit_amount_cents: int, customer: str
    ) -> pricing_pb2.PriceOrderResponse:
        request = pricing_pb2.PriceOrderRequest(
            sku=sku,
            quantity=quantity,
            unit_amount_cents=unit_amount_cents,
            customer=customer,
        )
        return await self._stub.PriceOrder(request, timeout=self._timeout_seconds)

    def is_ready(self) -> bool:
        state = self._channel.get_state(try_to_connect=True)
        return state not in (
            grpc.ChannelConnectivity.TRANSIENT_FAILURE,
            grpc.ChannelConnectivity.SHUTDOWN,
        )

    async def close(self) -> None:
        await self._channel.close()
```

`insecure_channel` is correct in this platform: the sidecar terminates mTLS, so TLS in the
application would be a second, redundant layer
([§9.4](#94-mtls-and-proving-it-is-actually-on)). The `timeout=` argument is the
deadline. Without it a synchronous hop turns a slow dependency into an outage — every request parks
on the event loop until the client gives up, and `order-api` stops answering for reasons that have
nothing to do with `order-api`.

**One channel per process, not per request.** Build it in the lifespan and drain it on shutdown, next
to Kafka and S3:

```python
state: dict = {"producer": None, "s3": None, "pricing": None, "ready": False}
```

```python
    state["pricing"] = PricingClient(
        settings.pricing_addr, settings.pricing_timeout_seconds
    )
    state["ready"] = True
    log.info("order-api started version=%s", settings.service_version)
    try:
        yield
    finally:
        state["ready"] = False
        await producer.stop()
        await state["pricing"].close()
        log.info("order-api stopped")
```

A gRPC channel is a long-lived, multiplexing object that manages its own connection pool and
reconnection. Creating one per request throws away the connection and pays a TCP and HTTP/2 handshake
on every order.

**Readiness gets a second condition.** If the channel cannot connect, this pod cannot serve orders and
should be pulled out of the Service rather than answering 502s:

```python
@app.get("/readyz")
def readyz() -> dict:
    """Readiness: dependencies are up. Kubernetes pulls us out of the Service if this fails."""
    if not state["ready"]:
        raise HTTPException(status_code=503, detail="dependencies not ready")
    pricing = state["pricing"]
    if pricing is None or not pricing.is_ready():
        raise HTTPException(status_code=503, detail="pricing channel not ready")
    return {"status": "ready"}
```

`get_state(try_to_connect=True)` both reads the channel state and nudges an idle channel into
connecting, so readiness is what recovers a pod after `pricing` comes back.

**The call.** One helper, so there is exactly one place that decides what a pricing failure means:

```python
async def _price_order(order: OrderIn) -> pricing_pb2.PriceOrderResponse:
    """Call shop.v1.Pricing/PriceOrder. Raises HTTPException(502) on any failure —
    never falls back to a locally computed price, so a pricing outage is a visible
    order failure rather than a silently wrong total."""
    pricing = state["pricing"]
    try:
        response = await pricing.price_order(
            sku=order.sku,
            quantity=order.quantity,
            unit_amount_cents=order.amount_cents,
            customer=order.customer,
        )
    except grpc.RpcError as exc:
        code = exc.code()
        result = "timeout" if code == grpc.StatusCode.DEADLINE_EXCEEDED else "error"
        PRICING_CALLS.labels(result=result, served_by="unknown").inc()
        log.warning("pricing call failed sku=%s code=%s", order.sku, code)
        raise HTTPException(status_code=502, detail="pricing unavailable") from exc
    PRICING_CALLS.labels(result="ok", served_by=response.served_by).inc()
    return response
```

`DEADLINE_EXCEEDED` is split out from every other status because "we were too slow" and "it was
broken" have different fixes, and a single `result="error"` bucket hides which one you have.

**In `create_order`**, price first, then persist. The price is part of the record, so an order that
cannot be priced must not reach S3 or Kafka at all:

```python
    try:
        pricing = await _price_order(order)

        payload = order.model_dump() | {
            "order_id": order_id,
            "created_at": created_at,
            "total_amount_cents": pricing.total_amount_cents,
            "priced_by": pricing.served_by,
        }
        body = json.dumps(payload, separators=(",", ":")).encode()
```

The exception handling needs a clause it did not have before, and its order matters:

```python
    except HTTPException:
        ORDERS_RECEIVED.labels(result="error").inc()
        raise
    except Exception:
        ORDERS_RECEIVED.labels(result="error").inc()
        log.exception("failed to ingest order_id=%s", order_id)
        raise HTTPException(status_code=502, detail="downstream failure")
```

Without the first clause the bare `except Exception` swallows the 502 from `_price_order` and
re-raises a generic one, losing `detail="pricing unavailable"` and logging a stack trace for a
downstream failure that was already handled and counted.

Finally, the response carries the pricing result through:

```python
    return {
        "order_id": order_id,
        "status": "accepted",
        "s3_key": key,
        "total_amount_cents": pricing.total_amount_cents,
        "discount_cents": pricing.discount_cents,
        "rule_applied": pricing.rule_applied,
        "priced_by": pricing.served_by,
    }
```

**`priced_by` is the field [§19.4](#194-the-frontend-vite-and-a-live-tally) tallies.** The frontend
places orders against `order-api`, counts `priced_by` across the responses and draws the ratio. That is the entire
mechanism by which an Istio weight change becomes something you watch in a browser — it is `served_by`
off the wire ([§18.1](#181-the-contract)), renamed once on the way out and never aggregated in
between.

**Nothing to add to `services/order-api/BUILD`.** Pants resolves `from shop.v1 import pricing_pb2` to
the generated target from the import itself
([§17.1](#171-the-problem-with-a-build-tool-per-language)), and `grpcio` is already in
`3rdparty/python/requirements.txt`. Confirm rather than assume:

```bash
pants dependencies --transitive services/order-api:bin | grep protos
# protos/shop/v1/pricing.proto:protos
```

**The tests.** A fake client, so the suite never opens a socket:

**`services/order-api/tests/test_api.py`**

```python
class _FakePricingClient:
    """Stands in for PricingClient so tests never touch the network."""

    def __init__(self, *, response=None, error: grpc.RpcError | None = None):
        self._response = response
        self._error = error

    async def price_order(self, **kwargs):
        if self._error is not None:
            raise self._error
        return self._response


class _FakeRpcError(grpc.RpcError):
    def __init__(self, code: grpc.StatusCode):
        self._code = code

    def code(self) -> grpc.StatusCode:
        return self._code
```

`grpc.RpcError` is a bare `Exception` subclass with no constructor of its own, so a real one cannot be
raised with a chosen status code — `_FakeRpcError` exists only to make `code()` answer.

The happy path asserts the response actually carries the price through:

```python
def test_order_response_includes_pricing_result():
    state["s3"] = _FakeS3()
    state["producer"] = _FakeProducer()
    state["pricing"] = _FakePricingClient(
        response=pricing_pb2.PriceOrderResponse(
            total_amount_cents=4499,
            discount_cents=500,
            rule_applied="volume-discount",
            served_by="pricing-v1",
        )
    )

    result = asyncio.run(create_order(_order()))

    assert result["status"] == "accepted"
    assert result["total_amount_cents"] == 4499
    assert result["discount_cents"] == 500
    assert result["rule_applied"] == "volume-discount"
    assert result["priced_by"] == "pricing-v1"
```

And both failure modes get their own test, because they take different branches through
`_price_order`:

```python
def test_pricing_timeout_returns_502():
    from fastapi import HTTPException

    state["s3"] = _FakeS3()
    state["producer"] = _FakeProducer()
    state["pricing"] = _FakePricingClient(
        error=_FakeRpcError(grpc.StatusCode.DEADLINE_EXCEEDED)
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(create_order(_order()))

    assert exc_info.value.status_code == 502


def test_pricing_unavailable_returns_502():
    from fastapi import HTTPException

    state["s3"] = _FakeS3()
    state["producer"] = _FakeProducer()
    state["pricing"] = _FakePricingClient(
        error=_FakeRpcError(grpc.StatusCode.UNAVAILABLE)
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(create_order(_order()))

    assert exc_info.value.status_code == 502
```

These are the tests that keep the no-fallback decision from being quietly reversed later. A fallback
added without touching them would leave both passing only if it still returned 502, which is the
point.

```bash
pants test services/order-api:tests
```

Once the images are built and Argo CD has synced, the call is visible end to end:

```bash
curl -s -X POST http://shop.localtest.me/orders \
  -H 'content-type: application/json' \
  -d '{"customer":"ada","sku":"W-1","quantity":3,"amount_cents":4999}' | jq .
```

A `priced_by` of `pricing-v1` or `pricing-v2` in that response means the hop works. Repeat it and
watch which version answers — that is the canary, in one command, before the frontend exists.

### 19.2 `pex_binary`, and the one flag that decides whether it runs


A PEX is a single executable zip containing your code and its entire dependency closure. `python
order-api.pex` runs it; there is no `pip install` step at any point after Pants.

First, describe the platform the PEX will actually run on. Generate it from a real container rather
than writing it by hand:

```bash
docker run --rm python:3.13-slim sh -c \
  'pip install pex && pex3 interpreter inspect --markers --tags' > 3rdparty/python/linux.json
```

**`3rdparty/python/BUILD`** (comments stripped):

```python
python_requirements(
    name="reqs",
    source="requirements.txt",
)

file(
    name="linux-platform",
    source="linux.json",
)
```

**`services/pricing/BUILD`**, the `pex_binary` (comments stripped):

```python
pex_binary(
    name="bin",
    entry_point="pricing/main.py:main",
    dependencies=[":lib"],
    complete_platforms=["3rdparty/python:linux-platform"],
    output_path="pricing.pex",
)
```

`complete_platforms` goes on **every** `pex_binary` in the repo, including the one the Backstage
skeleton emits. The cluster is `linux/aarch64`; the laptop is not, and `grpcio`, `pydantic-core`,
`uvloop` and `watchfiles` are all native extensions — without it `pants package` resolves macOS wheels
into an artifact that builds, tests and pushes cleanly and then fails to import inside the container.
Check the result:

```bash
unzip -l dist/pricing.pex | grep -E 'manylinux|macosx' | head
```

You want `manylinux2014_aarch64` in the wheel filenames, not `macosx`.

`output_path` exists so the artifact lands at `dist/pricing.pex` rather than the default
`dist/services.pricing/bin.pex`, which is what lets `dist/` be used directly as a Buildah build
context and the Dockerfile `COPY` by name.

> **One constraint follows from cross-packaging.** Every platform-specific dependency must be
> available as a **prebuilt wheel** for the target — Pants can only build sdists for the local
> machine. A dependency that ships source-only for `linux/aarch64` cannot be cross-packaged at all;
> you would have to build the wheel yourself and host it in [[sonatype-nexus]]. This is not a Pants
> quirk. Any tool that resolves wheels on the build host and ships them elsewhere has it, and it is
> the same class of mistake as building a Go binary with `CGO_ENABLED=1` and putting it in `scratch`.

The Dockerfile that consumes it is the whole payoff:

```dockerfile
# syntax=docker/dockerfile:1.7
FROM docker.io/library/python:3.13-slim

RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin appuser

WORKDIR /app
COPY --chown=10001:10001 pricing.pex /app/pricing.pex

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER 10001
# 50051 gRPC, 9090 the health/metrics HTTP server.
EXPOSE 50051 9090
ENTRYPOINT ["python", "/app/pricing.pex"]
```

No `uv sync`, no layer-caching strategy, no index configuration, no build-time network access at all.
Compare it to [§3.1](#31-order-api-python--fastapi)'s multi-stage Dockerfile and the
argument makes itself.

### 19.3 A PEX needs somewhere to write, and `readOnlyRootFilesystem` gives it nowhere


A PEX is a zip that **unpacks its dependency closure on first run**. The bootstrap extracts wheels to
`PEX_ROOT`, which must be writable, and falls back to the temp directory when it is not — so under
`readOnlyRootFilesystem: true` every candidate fails and the process dies before importing a line of
your code. None of your logging configuration has run at that point, so `kubectl logs` shows nothing
at all.

Give it a writable `/tmp` and point `PEX_ROOT` at it explicitly, keeping the root filesystem
read-only. From `deploy/charts/order-platform/templates/pricing.yaml`:

```yaml
          env:
            # ... the service's own config ...
            - name: PEX_ROOT
              value: "/tmp/pex"
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities: { drop: ["ALL"] }
          volumeMounts:
            - { name: tmp, mountPath: /tmp }
      volumes:
        - { name: tmp, emptyDir: {} }
```

Set `PEX_ROOT` rather than relying on `/tmp` being writable by default — the fallback order is an
implementation detail, and an explicit path is a thing a reader can find. **Every service packaged as
a PEX needs both halves** — `order-api.yaml`, `pricing.yaml` and `scaffolded.yaml` all carry them, so
a service that arrives through the paved path gets them without anyone remembering to ask.

It is the same class of problem as `nginx-unprivileged` needing writable `/tmp`, `/var/cache/nginx`
and `/var/run`: both render perfectly under `helm template`, pass `kubectl apply --dry-run=server`,
and fail only at runtime. **Dry-run validates schema, not whether the process can start.**

```bash
kubectl -n shop get pods -l app.kubernetes.io/name=pricing
# pricing-v1-... 2/2 Running     (2/2 — the sidecar is the second container)
# pricing-v2-... 2/2 Running
```

### 19.4 The frontend: Vite, and a live tally


`frontend/` is a [[vite]] + TypeScript page with no framework. It POSTs orders to `order-api`,
tallies the `priced_by` on each response, and draws a bar. A 90/10 → 50/50 weight change is visible in a
browser within seconds.

It is a demo dashboard, and it earns its place for one reason: **it makes the canary a thing you watch
rather than a thing you query.** The same information is in Prometheus. Nobody stands at a Prometheus
console watching a ratio move.

**`frontend/BUILD`**

```python
package_json(
    scripts=[
        node_build_script(
            entry_point="build",
            output_directories=["dist"],
        ),
    ],
    dependencies=[
        ":npmrc",
        ":tsconfig",
        ":vite_config",
        ":index_html",
        "./src",
        "./src:style_css",
    ],
)

file(name="npmrc", source=".npmrc")
file(name="tsconfig", source="tsconfig.json")
file(name="vite_config", source="vite.config.ts")
file(name="index_html", source="index.html")

# Not part of the Vite build — it is COPYed into the image and read by the
# port-consistency check in `checks/`.
file(name="nginx_conf", source="nginx.conf")
```

**Every dependency there is listed by hand, and that is the rule for non-Python targets.** Pants
infers dependencies from *imports*, and a build script's inputs are not imports: `tsconfig.json`,
`vite.config.ts`, `index.html` and `src/style.css` are invisible to inference. Omitting a config file
fails loudly. Omitting an asset does not fail at all — Vite builds successfully in a sandbox that
simply does not contain `style.css` and emits a bundle with no styles, which is a broken page and a
green build. Enumerate the inputs; do not trust inference outside Python.

One deliberate inconsistency: the frontend's Dockerfile runs the Vite build itself in a `node` stage
rather than copying a Pants artifact, unlike the other three. The reason is that a static bundle is
platform-independent — it has none of the cross-compilation problem
[§19.2](#192-pex_binary-and-the-one-flag-that-decides-whether-it-runs) exists to solve — so the
artifact handoff buys nothing here. Worth revisiting if the node stage gets slow. It is recorded
rather than smoothed over because an unexplained inconsistency is how the next person concludes the
pattern does not matter.

The frontend gets its own Ingress on **`app.localtest.me`**, not `shop.localtest.me`. `order-api`
already owns that host ([§10.1](#101-one-chart-two-workloads)) and
ingress-nginx's admission webhook rejects a duplicate host/path outright.

### 19.5 One CI step instead of two


The Python step and the Go step are gone. In their place, one step in `.buildkite/pipeline.sh`:

```yaml
  - label: ":hammer: lint · typecheck · test · package"
    key: verify
    agents: { queue: kubernetes }
    artifact_paths: "dist/*"
    plugins:
      - kubernetes:
          podSpec:
            imagePullSecrets:
              - name: nexus-pull
            containers:
              - image: nexus:8082/ci/pants:0.13.2
                resources:
                  requests: { cpu: "1", memory: 2Gi }
                  limits:   { memory: 4Gi }
                command:
                  - |
                    set -euo pipefail

                    git config --global --add safe.directory "$PWD"

                    pants lint check test ::

                    pants package $(ls -d services/*/BUILD | sed 's#/BUILD#:bin#')

                    ls -la dist/
```

Four things about this are load-bearing:

**The step runs a prebuilt Pants image out of Nexus**, `.buildkite/pants-ci.Dockerfile`, rather than
installing Pants per build. It carries the checksum-verified `scie-pants` launcher from
[§17.3](#173-pantstoml), a Go toolchain matching `services/order-worker/go.mod` (Pants *searches* for
`go`, it does not download one), and `unzip`/`zip`/`xz`, which Pants needs to unpack the tools it does
download — protoc, ruff, the Go SDK.

**`pants package` runs here, not in the image build.** The Buildah pods below it contain Buildah and
nothing else — no Python, no Go, no Node, no compiler. They `buildkite-agent artifact download` the
artifacts and copy them into an image. That is why every Dockerfile under `services/` is now four
lines, and why the **build context is `dist/`** rather than the source tree:

```sh
buildah bud \
  --tls-verify=false \
  --file services/$SVC/Dockerfile \
  --tag "$REGISTRY/shop/$SVC:$SHA" \
  --tag "$REGISTRY/shop/$SVC:latest" \
  dist
```

The last argument is the context. Each Dockerfile therefore `COPY`s its artifact by bare name —
`order-api.pex`, `pricing.pex`, `order-worker` — which is what the `output_path` on each Pants target
exists to guarantee. A `COPY services/order-api/…` would fail with "no such file or directory" on a
path that exists perfectly well in the repo.

`order-worker`'s Dockerfile is the whole of it, and it has one flag the PEX images do not need:

```dockerfile
# syntax=docker/dockerfile:1.7
FROM gcr.io/distroless/static-debian12:nonroot
COPY --chmod=0755 order-worker /order-worker
USER 65532:65532
EXPOSE 9090
ENTRYPOINT ["/order-worker"]
```

`--chmod=0755` is required, not cosmetic. `pants package` writes an executable binary, but the verify
step uploads it as a Buildkite artifact and the build step downloads it, and **artifact transfer does
not preserve file modes** — the bit is lost between the two pods and the container fails at runtime
with `exec: "/order-worker": permission denied`, with no application output at all. The PEX services
are immune only because they are invoked as `python /app/x.pex` rather than executed directly.

**Both the package targets and the build steps are discovered, not listed.** A directory under
`services/` with a `BUILD` file and a `Dockerfile` is a service, and that is the whole contract:

```sh
SERVICES="$(cd services && ls -d */ 2>/dev/null | sed 's#/##' | while read -r s; do
  [ -f "$s/BUILD" ] && [ -f "$s/Dockerfile" ] && echo "$s"
done | sort | tr '\n' ' ')"
```

`BUILD` rather than `Dockerfile` alone is the honest signal: a directory Pants does not know about
cannot be linted, tested or packaged, so it is not a service this pipeline can deliver. The Backstage
skeleton emits both files, which is what lets the paved path
([§14.6](#146-paved-path-1--a-new-service)) add a service without anyone
editing CI.

**There are no `--build-arg`s.** The version a running service reports comes from `SERVICE_VERSION`,
set by the Helm chart from the image tag
([§10.1](#101-one-chart-two-workloads)) — one mechanism, applied uniformly
to Python and Go alike, rather than a Go-specific link-time stamp that only one of the four images
could ever have carried.

The frontend and the portal get their own steps: neither consumes a Pants artifact, and the portal's
build is measured in double-digit minutes, so it is `branches: "main"` only.

### 19.6 Two checks nothing else would catch


Some facts span two files in two languages with nothing connecting them. Those get a test.

**The OpenAPI spec is derived, not authored.** Backstage's catalog reads `services/order-api/openapi.json`
from git, but FastAPI builds that document from route signatures at runtime, so the checked-in copy
can only ever be a snapshot. `services/order-api/BUILD` makes regenerating it a target, and a test
fails when the two drift:

```python
python_sources(
    name="tools",
    sources=["openapi_dump.py"],
    dependencies=[":lib"],
)

pex_binary(
    name="dump-openapi",
    entry_point="openapi_dump.py",
    dependencies=[":tools"],
)

resource(
    name="openapi-spec",
    source="openapi.json",
)
```

```bash
pants run services/order-api:dump-openapi > services/order-api/openapi.json
```

`:openapi-spec` is a `resource`, not code, so nothing infers it — the drift test reads it off disk by
path, which is why `python_tests` lists it explicitly in `dependencies`. A hand-maintained API spec is
a lie with a timestamp on it.

**The frontend's proxy port must match the port `order-api`'s Service publishes.** `frontend/nginx.conf`
says `proxy_pass http://order-api.shop.svc.cluster.local:80/orders`; the chart says
`- { name: http, port: 80, targetPort: http }`. Point nginx at 8000 — order-api's *container* port,
which nothing serves on the ClusterIP — and every order in the dashboard reads `HTTP 502` while a
direct `curl` at order-api returns 202, sending you to look at the wrong service entirely. The chart
is valid, the nginx config is valid, both images build, every pod is Ready. So `checks/` at the repo
root asserts the two agree:

```python
python_tests(
    name="tests",
    sources=["test_*.py"],
    # Config files from two other directories, read as plain text. Nothing
    # infers these — there is no import to follow, which is exactly why the two
    # were free to drift apart in the first place.
    dependencies=[
        "frontend:nginx_conf",
        "deploy/charts/order-platform:order-api-template",
    ],
)
```

**`deploy/charts/order-platform/BUILD`**, and note where it is *not*:

```python
# Deliberately NOT in templates/. Helm renders every file under templates/ as a
# manifest, so a BUILD file there fails the whole chart with
# `YAML parse error on order-platform/templates/BUILD`.
file(name="order-api-template", source="templates/order-api.yaml")
```

That is the pattern worth taking away: **when a fact is duplicated across a language boundary, the
monorepo lets you assert it in a unit test.** It is the same argument as
[§18.2](#182-generate-and-look-at-what-came-out), applied to config instead of to a `.proto`.

### 19.7 Commit


Two files are now dead. `order-api`'s dependencies are resolved from `locks/python-default.lock`
by Pants, so the uv pair that used to do it describes a build nobody runs — and a stale lockfile is
worse than none, because the next person to read it will believe it.

```bash
git rm services/order-api/pyproject.toml services/order-api/uv.lock
```

Then verify and commit:

```bash
pants lint check test ::
pants package services/order-api:bin services/order-worker:bin services/pricing:bin
ls -la dist/

git add pants.toml 3rdparty locks protos services frontend checks .buildkite deploy
git commit -m "build: pants as the monorepo build system, one proto for two languages"
git push
```

`git push` builds all four images and Argo CD deploys them, exactly as
[Phase 3](#) set up — the delivery path did not change, only what feeds it.

---

## Where you are

One command lints, typechecks, tests and packages three languages, and it needs no edit when a fourth
arrives. One `.proto` is compiled by both Python and Go, so a change to the contract fails on your
laptop rather than in a consumer at 3am. The images are `FROM` plus `COPY`, which means the privileged
Buildah pod no longer resolves anything from a network.

And there is now a synchronous call between two of your services — which is what
[§9.8](#98-canary-two-versions-of-pricing-behind-one-service) needs to shift
traffic between two versions of `pricing` and let you watch the split move in a browser. Go back and
do that now; it is the part of [Phase 4](#) you could not run yet.

**Next: [Phase 6 — Operating it](#).** Now find out what happens when it breaks.

[← All phases](docs/README.md) · [← Phase 5 — Making it someone else's platform](#) · [Phase 6 — Operating it, and taking it down →](#)

---

## Appendix A — Version matrix

Verified 2026-08-16 against a running cluster — every version below was read back from the live workload or the installed chart, not from a changelog. Re-check before you start; these move.

| Component | Version | How to check |
|---|---|---|
| kind | v0.32.0 | `kind version` / [releases](https://github.com/kubernetes-sigs/kind/releases) |
| Helm | ≥ 3.8.0 (OCI required) | `helm version --short` |
| ingress-nginx | controller-v1.13.0 | [releases](https://github.com/kubernetes/ingress-nginx/releases) — **note:** v1.13.0's kind manifest dropped the `ingress-ready` nodeSelector; [§4.3](#43-install-the-ingress-controller) patches it back |
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
| Yarn | 4.18.0 — whatever `create-app` pins in `packageManager`; **never downgrade** ([§14.3](#143-scaffold-the-portal)) | `yarn --version` |
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
| `ImagePullBackOff` on `nexus:8082/...` | containerd can't reach or auth to Nexus | `docker exec devops-worker curl -s -o /dev/null -w '%{http_code}' http://nexus:8082/v2/` — expect `401`. Not `401`? Re-run [§5.9](#59-teach-containerd-on-the-kind-nodes-about-nexus). `401` but still failing? The pod is missing `imagePullSecrets` or the ExternalSecret hasn't synced. |
| `curl http://localhost` returns **`000`** | Ingress controller scheduled on a node with no port mappings | `000` = nothing listening, not a 404. `kubectl -n ingress-nginx get pods -o wide` — if `NODE` isn't `devops-control-plane`, apply the `ingress-ready` nodeSelector patch in [§4.3](#43-install-the-ingress-controller). Upstream dropped that selector in controller-v1.13.0. |
| Ingress Service stuck `EXTERNAL-IP <pending>` | `type: LoadBalancer` with no cloud provider | Harmless on kind — traffic arrives via `hostPort`, not the Service. Don't install MetalLB to "fix" it. |
| Pods can't resolve `nexus` | Nexus container got a new IP | Re-run [§5.10](#510-teach-pods-about-nexus-coredns) with the current `docker inspect nexus` IP. |
| `docker push` → `http: server gave HTTP response to HTTPS client` | `insecure-registries` not applied | [§5.8](#58-trust-the-plain-http-registry-from-docker), then **restart Docker**. |
| `docker login nexus:8082` → 401 with correct password | Docker Bearer Token Realm not active | Nexus → ⚙ → Security → Realms → activate it ([§5.4](#54-create-the-docker-hosted-registry)). |
| CI: `go: ... 401 Unauthorized` from `nexus:8081`, or `uv sync` hangs | Anonymous access disabled in Nexus | Builds pass no credentials to the proxies. Enable global anonymous access ([§5.3](#53-run-nexus)); Docker pull stays authenticated via the per-repository switch. Check with `curl -o /dev/null -w '%{http_code}' http://nexus:8081/repository/pypi-proxy/simple/` — expect `200`. |
| CI: `uv sync --locked` → "lockfile needs to be updated", but it passes locally | `uv.lock` records a different registry than the build resolves against | Declare the index in `pyproject.toml` via `[[tool.uv.index]]` and re-run `uv lock` ([§3.1](#31-order-api-python--fastapi)). Setting the index only in CI can never match a committed lock. |
| CI: `go: -race requires cgo` | Test step on an alpine Go image | `golang:1.26-alpine` is `CGO_ENABLED=0` with no gcc. Use `golang:1.26` for the test step ([§12.5](#125-the-pipeline)). |
| Build fails cloning `buildkite-plugins/kubernetes-buildkite-plugin` | The Buildkite queue is **Hosted**, not Self-hosted | The job ran on Buildkite's machines, which don't understand the `kubernetes` plugin. Queue type can't be changed after creation — delete it and recreate as Self-hosted ([§12.2](#122-create-the-buildkite-side)). |
| `agent-stack-k8s` logs `job tags do not match expected tags in configuration` | Same as above | A hosted agent adds `namespace-experiments=docker.builder=local`; your controller advertises only `queue=kubernetes`. |
| ClusterSecretStore `Invalid` | OpenBao SA lacks TokenReview, or role name mismatch | `kubectl -n external-secrets logs deploy/external-secrets`. Check the `system:auth-delegator` binding and that the role is `eso` bound to SA `external-secrets` in ns `external-secrets`. |
| ExternalSecret `SecretSyncedError`, `permission denied` | KV v2 path missing the `/data/` segment | The policy must be `path "shop/data/*"`, not `path "shop/*"` ([§7.4](#74-configure-kubernetes-authentication)). |
| Kafka pods `Pending` | No PVs / insufficient resources | `kubectl -n kafka describe pod <pod>`. On kind the default local-path provisioner needs disk — check Docker's disk allocation. |
| `kubectl wait kafka/orders` times out | Controllers haven't formed a quorum | `kubectl -n kafka logs orders-controller-0`; `kubectl -n kafka describe kafka orders` and read `.status.conditions`. |
| Argo CD `Unknown` / `ComparisonError` | Repo unreachable or chart won't render | `argocd app get order-platform`; `helm template` locally ([§10.3](#103-render-it-before-you-trust-it)). |
| Argo CD stuck `OutOfSync` after a green build | The deploy commit never landed | Check the Buildkite `bump image tags` step logs; usually a bad or expired GitHub PAT. |
| Buildkite agent never connects | Wrong token, or wrong cluster | `kubectl -n buildkite logs deploy/agent-stack-k8s`. Token must come from the **cluster's** agent tokens page, and the queue must exist. |
| Build step Pending forever | Queue tag mismatch | The step's `agents: { queue: kubernetes }` must equal the controller's `config.tags` value. |
| Buildah `cannot set up namespace` | Not privileged | The `securityContext.privileged: true` in [§12.5](#125-the-pipeline) is required for this approach. |
| Prometheus target missing | PodMonitor matched nothing | The monitor scrapes `portNumber: 15020`, the sidecar's merged endpoint, so a pod with no sidecar has nothing to scrape. (15020 is unnamed, which is why the monitor uses `portNumber:` and not `port:`; `http-envoy-prom` is 15090 and carries Envoy's own metrics only.) Check `READY 2/2` first, then labels ([§9.6](#96-the-metrics-problem-you-just-created)). |
| Grafana dashboard doesn't appear | ConfigMap label wrong | Must be `grafana_dashboard: "1"` and `sidecar.dashboards.searchNamespace: ALL`. |
| Everything is slow / pods OOMKilled | Docker memory too low | 16 GB minimum with the mesh and portal running ([§1.3](#13-give-docker-enough-room)). Check with `kubectl top nodes`. |
| Pod stuck `1/2 Running`, app fine | Sidecar can't reach `istiod` | `kubectl -n istio-system logs deploy/istiod`; `istioctl proxy-status` lists proxies and whether they're synced. |
| `RBAC: access denied` on every request | An `AuthorizationPolicy` matched and denied | `istioctl analyze -n shop` first — the usual cause is a `principals` value naming a ServiceAccount that doesn't exist, which denies everything and looks healthy in `kubectl get pods` ([§9.5](#95-authorization-deny-by-default-then-allow-the-paths-that-exist)). |
| `curl` from another namespace → `Connection reset by peer` | STRICT mTLS, and the caller has no sidecar | Working as designed. Enroll the caller's namespace, or confirm you meant to be outside the mesh. |
| A Job never completes, pod sits at `1/2` | Sidecar outlives the job container | Add `sidecar.istio.io/inject: "false"` to the **pod template** ([§9.3](#93-enroll-namespaces--and-decide-deliberately-which-ones)). |
| Kiali graph is empty | No traffic, or `istio_requests_total` missing | Send requests first. Still empty? Query `istio_requests_total` in Prometheus — if it's absent, the PodMonitor isn't scraping the merged endpoint. |
| Backstage template fails at the last step, `action not found` | Scaffolder GitHub module not registered | `backend.add(import('@backstage/plugin-scaffolder-backend-module-github'))` in `packages/backend/src/index.ts`, then rebuild the image ([§14.3](#143-scaffold-the-portal)). |
| Scaffolder PR fails with 403 | Fine-grained PAT missing `Pull requests: RW` | Contents alone is not enough to open a PR. Re-scope the token, update the value in OpenBao, wait for ESO to resync, restart the pod. |
| Scaffolded service builds but never deploys | Chart file missing or malformed | `helm template deploy/charts/order-platform` and look for it. The chart reads `services/*.yaml` — a file that isn't valid YAML renders as nothing, with no error ([§14.6](#146-paved-path-1--a-new-service)). |
| Every page returns `upstream connect error ... reset reason: connection termination` | Ingress backend is in the mesh under STRICT mTLS | Not a dead backend — a refused plaintext connection. NGINX proxies to pod IPs (which name no service for Istio to originate mTLS to) and preserves the browser's `Host:` (which Envoy routes on, and which matches no mesh service). Both annotations are required and are already in the chart: `nginx.ingress.kubernetes.io/service-upstream: "true"` and `nginx.ingress.kubernetes.io/upstream-vhost: "<svc>.<ns>.svc.cluster.local"`. Confirm with the source sidecar's stats — `destination_service_name.PassthroughCluster` means the mesh could not identify the destination. |
| A `200` at the edge, but is mTLS actually on? | Source-side stats report `unknown` even when it is | Read the **destination** reporter: `kubectl -n shop exec deploy/order-api -c istio-proxy -- pilot-agent request GET 'stats?filter=istio_requests_total' \| grep reporter.destination`. Look for `connection_security_policy.mutual_tls` and a real `source_principal`. A `200` alone proves only that bytes moved — plaintext through `PassthroughCluster` returns `200` too. |
| A credential you just wrote to OpenBao is still rejected | ESO polls on `refreshInterval`; the Secret still holds the old value | The `ExternalSecret` reports `Ready=True` the whole time, truthfully — it is synced, to the previous value. Restarting the consumer does not help. Force it: `kubectl -n <ns> annotate externalsecret <name> force-sync="$(date +%s)" --overwrite`, then restart. Diagnose without printing the secret: compare decoded **length** (`... \| base64 -d \| wc -c`) and `bao kv metadata get <path>`'s newest `created_time` against `.status.refreshTime`. |
| Argo reports `Synced` but the live resource is on an old image | Stale cache in the application controller | `kubectl -n argocd annotate app <name> argocd.argoproj.io/refresh=hard --overwrite`. Suspect this when `Synced` and `Degraded` appear together and the rendered manifest in git plainly differs from the live object. |
| `exec /order-worker: no such file or directory` on a file that exists and is executable | The binary is dynamically linked; `distroless/static` has no loader | It is the *loader* that is missing, not the binary. Pants defaults `[golang] cgo_enabled` to true — `pants.toml` sets it to `false` ([§17.2](#)). Check with `readelf -l <binary> \| grep interpreter`: a static binary has no `PT_INTERP`. |
| Every order in the dashboard reads `HTTP 502`, but `curl` against the API returns `202` | The frontend proxies to a port the Service does not publish | Two different paths; only the browser's is broken. `frontend/nginx.conf` must target the **Service** port (`80`), not the container port (`8000`). `checks/` contains a test that fails when the two disagree. |
| Backstage loads a white screen over `http://` | `crypto.randomUUID` is unavailable in an insecure context | Use the `https://` URL. This is a browser restriction, not a Backstage bug. |
| Pods cannot resolve `nexus` after a Docker restart | The Nexus container came back on a different bridge IP | The CoreDNS `hosts` entry pins an IP. Re-run [§5.10](#510-teach-pods-about-nexus-coredns) with the current `docker inspect nexus` address. |

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
| **TLS at the edge and to Nexus** | Pod-to-pod is mTLS via Istio ([§9.4](#94-mtls-and-proving-it-is-actually-on)), but the browser→nginx hop, Nexus and OpenBao are still plaintext | cert-manager for issuance, then real certificates on the ingress and on Nexus |
| **Supply-chain security** | No SBOM, no image signing, no vulnerability gate | Syft for SBOMs, Grype/Trivy scanning as a pipeline step, Cosign + Sigstore for signatures, Kyverno to reject unsigned images at admission |
| **Policy enforcement** | Nothing stops a privileged pod being deployed | Kyverno or Gatekeeper; Pod Security Admission at `restricted` on workload namespaces |
| **NetworkPolicies** | Istio authorizes *requests* by identity; nothing yet restricts *packets*. A workload outside the mesh is unconstrained | Default-deny per namespace, then allow-list. Complementary to [§9.5](#95-authorization-deny-by-default-then-allow-the-paths-that-exist), not a substitute for it |
| **Logs and traces** | Metrics only — you can see *that* it broke, not *why* | Loki for logs, Tempo + OpenTelemetry for traces. Grafana already fronts all three |
| **Progressive delivery** | Deploys are all-or-nothing | Argo Rollouts or Flagger for canary/blue-green, gated on the Prometheus metrics you already export |
| **HA and autoscaling** | Fixed replica counts, single Argo CD/OpenBao | HPA on custom metrics (consumer lag), Argo CD HA manifests, OpenBao with Raft + auto-unseal |
| **Real IaC** | The cluster itself is imperative (`kind create`), and the infra paved path emits one-shot Jobs rather than reconciled resources | Terraform/OpenTofu, or Crossplane so [§14.7](#147-paved-path-2--infrastructure) produces an `S3Bucket` custom resource that a controller keeps true |
| **Traces from the mesh** | Envoy can emit spans for every hop and we collect none of them | Tempo + OpenTelemetry; Istio needs only `meshConfig.defaultConfig.tracing` pointed at the collector, and Kiali will then link graph edges to traces |
| **Portal identity** | Backstage runs on guest auth with one shared GitHub token | GitHub OAuth for users, plus a GitHub App so scaffolder PRs are attributed to the person who filled in the form ([§14.8](#148-build-and-deploy-the-portal)) |
| **Least-privilege Nexus role** | We used `nx-admin` for the CI user | Build the scoped privilege list ([§5.5](#55-create-a-ci-user)) — the quickest real improvement you can make |
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

[← All phases](docs/README.md) · [← Phase 6 — Operating it, and taking it down](#)

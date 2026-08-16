# Phase 0 — Foundations

[← All phases](README.md) · [Phase 1 — The application, running →](phase-1-the-application.md)

> **Where this starts:** an empty laptop.
> **Where it ends:** a three-node Kubernetes cluster with a working edge, and an artifact repository
> that your laptop *and* the cluster nodes can both reach by the same name.

Nothing in this phase runs your code. That is the point — every later phase assumes a cluster you can
route into and a registry you can push to, and debugging those two while also debugging an
application is how people give up on this.

The one genuinely hard part here is [§5.2](#52-networking-the-part-everyone-gets-wrong): making the name
`nexus` mean the same thing in three different resolvers. Get that wrong and you get
`ImagePullBackOff` in Phase 1 that looks like a permissions bug and isn't.

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

> Node and Yarn are only needed for Backstage ([§14](phase-5-developer-portal.md#14-backstage-paved-paths-not-documentation)). `istioctl` is not required to install Istio — we use Helm for that — but `istioctl analyze` and `istioctl proxy-status` are the two commands that turn a silent mesh misconfiguration into a readable error, and you will want them.

### 1.3 Give Docker enough room

The cluster will run Kafka, Prometheus, Argo CD, OpenBao, Floci, Istio, Backstage and your apps simultaneously.

In Docker Desktop: Settings → Resources → set **CPUs ≥ 6**, **Memory ≥ 16 GB**, **Disk ≥ 80 GB**. Apply & Restart.

> **Where the extra memory goes**, since "just give it more RAM" is not an explanation. Istio adds `istiod` (~500 MB) plus an Envoy sidecar of roughly 50–100 MB to *every* pod in an enrolled namespace — with two replicas each of two services, plus Floci and the ingress controller, that is most of a gigabyte. Backstage adds a Node backend and its own PostgreSQL, and its **image build** is the real spike: a `vfs`-backed Buildah pod doing a full `yarn install` will transiently want several gigabytes of disk. If you are capped at 12 GB, the honest advice is to skip the mesh, or run it in ambient mode ([§9.1](phase-4-service-mesh.md#91-what-a-mesh-actually-buys-you-here--and-what-it-doesnt)) where one `ztunnel` per node replaces every sidecar.

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

> **Tradeoff — mono-repo vs. split app/config repos.** Putting manifests next to code means one PR can change both, and there is no cross-repo version skew to reason about. The cost: CI writes a commit back into the same repo it just built from, so you must guard against the deploy commit re-triggering a build (we do, in [§12.5](phase-3-delivery.md#125-the-pipeline)). At scale, teams split them — a separate `*-deploy` repo gives config its own review rules, its own access control, and no build/deploy commit loop. For one person on one laptop, mono-repo is strictly simpler. Take the split when more than one team writes to the manifests.

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

Don't push yet. We'll commit as we go and push at the end of [§3](phase-1-the-application.md#3-the-applications).

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
> It transfers to Artifactory as well, because the parts that matter are protocols, not products. A Docker registry is the OCI distribution API; a PyPI proxy is PEP 503's simple index; a Go proxy is the module proxy protocol. The client-side configuration in [§5.8](#58-trust-the-plain-http-registry-from-docker)–[§5.10](#510-teach-pods-about-nexus-coredns) — `insecure-registries`, containerd's `hosts.toml`, `PIP_INDEX_URL`, `GOPROXY` — is unchanged against Artifactory, and Artifactory's repository types are Nexus's under other names: **local** = hosted, **remote** = proxy, **virtual** = group.
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
> does **not** give away `docker pull`, and [§7](phase-1-the-application.md#7-openbao-and-external-secrets)'s
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

> **A private Go proxy is not a reason to disable checksum verification.** A `go (proxy)` repository serves modules only, not checksum-database data — which is why the advice to set `GOSUMDB=off` behind a private proxy is so widespread, and why it is wrong. Sonatype documents the actual answer: create a **raw (proxy)** repository pointing at `https://sum.golang.org` with strict content-type validation off, then set `GOSUMDB='sum.golang.org <NEXUS_RAW_URL>'` — the database name stays, the fetch route changes. `GONOSUMDB=*` is documented only as the opt-out for people who do not want the cache ([Sonatype](https://help.sonatype.com/en/configure-go-with-nexus.html), as of 2026-08).
>
> This tutorial does not create that raw repository, and does not need to. `go.sum` already records a hash for every module in the build list, so the `go` command verifies locally against it and never consults the checksum database during a build — check that for yourself with `go mod verify` and a `go build -mod=readonly` with the network off. The database is consulted when a module is *added*, and that is exactly the moment you want it working. Turning it off buys nothing today and disarms verification for the next dependency someone adds, in a platform whose entire thesis is that Nexus is the supply-chain choke point ([§5.1](#51-what-nexus-is-actually-for)). For a genuinely private module the scoped escape is `GOPRIVATE=github.com/yourorg/*`, not a global switch.

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

That last command will fail with `ImagePullBackOff` — the `nexus-pull` secret doesn't exist yet. **That failure is the point.** It's the exact symptom you'd hit in production with a misconfigured pull secret, and [§7.6](phase-1-the-application.md#76-let-kubernetes-pull-from-nexus) fixes it properly, from OpenBao. Clean up:

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

**Next: [Phase 1 — The application, running](phase-1-the-application.md).** You will write two
services, stand up the infrastructure they need, and install them with Helm until an HTTP request
produces a row in a database.

[← All phases](README.md) · [Phase 1 — The application, running →](phase-1-the-application.md)

# Phase 4 — Identity between services

[← All phases](README.md) · [← Phase 3 — Delivery: git as the deploy button](phase-3-delivery.md) · [Phase 5 — Making it someone else's platform →](phase-5-developer-portal.md)

> **Where this starts:** services that trust each other because they share a network.
> **Where it ends:** every call authenticated by workload identity, a default-deny policy, and a
> picture of who talks to whom.

Up to now `order-api` can reach `floci` because nothing stops it. Anything else in the cluster can
too. This phase replaces "same network" with "proven identity" as the basis for trust.

**It will break your monitoring, and that is the most useful thing in this phase.** STRICT mTLS
refuses Prometheus' plaintext scrape, your Phase 2 dashboards go blank, and *nothing logs an error*.
[§9.6](#96-the-metrics-problem-you-just-created) is that failure and its fix. Security controls that
silently break observability are the normal case, not a surprise — meeting one here, where you caused
it and know exactly what changed, is much cheaper than meeting one at 3am.

---

## 9. Istio: the service mesh

### 9.1 What a mesh actually buys you here — and what it doesn't

Start with the uncomfortable part. The usual service-mesh demo has service A calling service B over HTTP, and mTLS between them is the punchline. **We don't have that shape.** `order-api` never calls `order-worker`; Kafka joins them, asynchronously and deliberately ([§8](phase-1-the-application.md#8-kafka-with-strimzi)). If you install a mesh here expecting the demo, you get an expensive no-op.

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

> **We keep ingress-nginx as the edge.** Istio can serve north-south traffic itself, and in production that is usually the right call — one proxy, one config language. Here nginx already owns `hostPort` 80/443 on the kind control-plane node ([§4.3](phase-0-foundations.md#43-install-the-ingress-controller)), and swapping it out means rewriting every `Ingress` in the tutorial as an `HTTPRoute` and recreating the cluster. We keep nginx and **enroll it into the mesh** instead, which is the documented way to put a third-party ingress in front of meshed workloads: nginx terminates the browser's connection and re-originates it as mTLS to `order-api`.

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

`shop` and `floci` are declared in *our* manifests ([§6.2](phase-1-the-application.md#62-deploy-floci-into-the-cluster), [§7.5](phase-1-the-application.md#75-install-external-secrets-operator)),
so their labels belong in git and are already there. Only `ingress-nginx` — whose namespace comes from
an upstream manifest we don't own — needs the imperative form:

```bash
kubectl label namespace ingress-nginx istio-injection=enabled --overwrite

kubectl get namespace -L istio-injection
```

> [!warning] **A `kubectl label` on a namespace Argo CD manages does not survive.**
> If you enrol `shop` and `floci` imperatively instead, it works — until the next teardown. Argo CD
> recreates those namespaces from the manifests, which is exactly what `CreateNamespace=true` and the
> `Namespace` objects in `deploy/platform/` are for, and the label does not come back with them.
> Everything then starts *looking* fine and behaving wrongly: pods come up `1/1` instead of `2/2`, so
> they have no sidecar, so STRICT mTLS refuses their traffic, so [[kiali]]'s graph is empty and the
> `PodMonitor` — which addresses the sidecar's telemetry port — matches nothing at all. No error is
> printed anywhere in that chain.
>
> This is the general GitOps rule the hard way: **once a resource is under Argo CD, every field of it
> is, including the ones you set by hand.** `ingress-nginx` is the exception here only because nothing
> in `deploy/` declares that namespace.

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

One thing in the `floci` namespace must **not** be injected — the bootstrap Job from [§6.3](phase-1-the-application.md#63-bootstrap-the-s3-bucket-and-dynamodb-table). That's why its pod template already carries the opt-out:

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

> **The service-account names are load-bearing.** These principals must match the ServiceAccounts the Helm chart creates in [§10.1](phase-1-the-application.md#101-one-chart-two-workloads). If the chart names them differently, the policy silently denies everything, and you will debug it as "Floci is down". `istioctl analyze -n shop` catches the mismatch; `kubectl get pods` does not.

### 9.6 The metrics problem you just created

Go and look at Prometheus. Every `order-platform` target you had green in
[Phase 2](phase-2-observability.md) is now down, and your Grafana panels are drawing flat lines.

Nothing logged an error. Nothing restarted. `kubectl get pods` says `2/2`.

STRICT mTLS means every connection into a meshed pod must present a client certificate.
Prometheus has no sidecar and no certificate, so its plaintext scrape of `order-api:8000/metrics` is
refused at the proxy — before your application ever sees it. The `ServiceMonitor` you enabled in
[§13.3](phase-2-observability.md#133-confirm-your-app-is-being-scraped) cannot work here, and no
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
> condition [§13.5](phase-2-observability.md#135-an-alert-that-means-something) argues you should page
> on.

### 9.7 Commit, and a word on what you cannot verify yet

```bash
git add deploy/platform/istio deploy/platform/floci-bootstrap.yaml
git commit -m "feat(platform): istio with strict mtls and default-deny authz"
```

`order-api` and `order-worker` don't exist yet, so §9.4's proof covers Floci only. The rest of the mesh — the ingress path, the authorization policies keyed on those two service accounts — becomes verifiable in [§11](phase-3-delivery.md#11-argo-cd-pull-based-delivery), when Argo CD deploys the chart into the now-enrolled `shop` namespace. If a page load returns `RBAC: access denied` at that point, the policy in §9.5 is what to read first, and `istioctl analyze -n shop` is what to run.

---

## Where you are

Every call between meshed workloads is mutually authenticated and encrypted with certificates you
never issued by hand. `floci` refuses anything that is not `order-api` or `order-worker`, by
identity — not by IP, which can be stolen. Kiali draws the graph, including the refusals.

Your monitoring survived, because you fixed it when it broke.

**Next: [Phase 5 — Making it someone else's platform](phase-5-developer-portal.md).**

[← All phases](README.md) · [← Phase 3 — Delivery: git as the deploy button](phase-3-delivery.md) · [Phase 5 — Making it someone else's platform →](phase-5-developer-portal.md)

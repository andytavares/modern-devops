# Phase 4 — Identity between services

[← All phases](README.md) · [← Phase 3 — Delivery: git as the deploy button](phase-3-delivery.md) · [Phase 5 — Making it someone else's platform →](phase-5-developer-portal.md)

> **Where this starts:** services that trust each other because they share a network.
> **Where it ends:** every call authenticated by workload identity, a default-deny policy, a picture
> of who talks to whom, and traffic you can shift between two versions of a service by editing a
> weight.

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

> **We keep ingress-nginx as the edge, and this is a deviation — read why before you copy it.**
> Istio documents two supported ways to get traffic into the mesh: its own **Gateway** (which its
> docs recommend, "to make use of the full feature set that Istio offers"), or a plain Kubernetes
> `Ingress` with `ingressClassName: istio`. **Enrolling a third-party ingress controller into the
> mesh is not one of them** — Istio's ingress documentation does not mention third-party
> controllers at all, and the two nginx annotations this requires are documented by ingress-nginx
> for unrelated purposes (`service-upstream` for zero-downtime deploys, `upstream-vhost` for
> setting the `Host` header). Neither vendor documents the combination. It is a widely used
> community pattern that lives in GitHub issues, not in anyone's docs.
>
> We do it here for one specific reason: nginx already owns `hostPort` 80/443 on the kind
> control-plane node ([§4.3](phase-0-foundations.md#43-install-the-ingress-controller)), and it is
> also the edge for Argo CD, Grafana, Kiali and Backstage — none of which are in the mesh. Moving
> the two meshed hostnames to an Istio Gateway means something else has to own those ports.
>
> **At work, use the Istio Gateway.** The production shape is an external load balancer forwarding
> to `istio-ingressgateway`, with `Gateway` + `VirtualService` doing the routing — which is exactly
> what the `DestinationRule` and `VirtualService` in [§9.8](#98-canary-two-versions-of-pricing-behind-one-service)
> already teach you to write. What you would delete is nginx's mesh enrolment and the two
> annotations, not the Istio config.

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

Before you apply it, every `Ingress` in the chart needs two annotations. `ingress-nginx` is enrolled
in the mesh and `shop` is about to become STRICT, so the edge has to address its backend in a way
Envoy can identify as a service — by ClusterIP rather than raw pod IPs, and with the upstream `Host:`
rewritten to the service FQDN, because Envoy routes HTTP by authority, not by address. This is the
`order-api` Ingress from [§10.1](phase-1-the-application.md#101-one-chart-two-workloads), with the
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
> something, and a synchronous call to shift. [Phase 7](phase-7-polyglot-monorepo.md) builds
> `pricing` — the first service-to-service request path in this platform
> ([§9.1](#91-what-a-mesh-actually-buys-you-here--and-what-it-doesnt) is blunt about there not being
> one until then). **Read this now, run it after [§19](phase-7-polyglot-monorepo.md#19-a-third-service-pex-packaging-and-a-dashboard).**
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
([§19.1](phase-7-polyglot-monorepo.md#191-pricing-deliberately-synchronous)).

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
operation**, which is the whole point of [Phase 3](phase-3-delivery.md). The bar moves within a sync
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
[Phase 7](phase-7-polyglot-monorepo.md) builds the `pricing` service they steer. Come back for them.

**Next: [Phase 5 — Making it someone else's platform](phase-5-developer-portal.md).**

[← All phases](README.md) · [← Phase 3 — Delivery: git as the deploy button](phase-3-delivery.md) · [Phase 5 — Making it someone else's platform →](phase-5-developer-portal.md)

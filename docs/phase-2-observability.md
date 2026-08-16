# Phase 2 — Seeing what it does

[← All phases](README.md) · [← Phase 1 — The application, running](phase-1-the-application.md) · [Phase 3 — Delivery: git as the deploy button →](phase-3-delivery.md)

> **Where this starts:** a working application you can only inspect with `kubectl logs`.
> **Where it ends:** a dashboard showing orders flowing, and one alert that would actually wake you
> for a real reason.

You have a system that works. You have no idea how *well* it works, and no way to be told when it
stops. That is the gap this phase closes, and it comes before delivery automation on purpose: **the
moment you can deploy quickly is the moment you need to know quickly whether the deploy was fine.**

Everything scraped here is scraped the simple way — Prometheus talks straight to your pods' `/metrics`.
[Phase 4](phase-4-service-mesh.md) breaks that, deliberately and instructively, and shows you the fix.

---

## 13. Observability with Grafana

### 13.1 What to install and why it's one chart

`kube-prometheus-stack` bundles the Prometheus Operator, Prometheus, Alertmanager, Grafana, node-exporter and kube-state-metrics, pre-wired with dashboards and recording rules for Kubernetes itself. Assembling those by hand is a week of work to arrive at a worse version of the same thing.

The Operator is the important part: it introduces `ServiceMonitor`, `PodMonitor` and `PrometheusRule` CRDs, so **applications declare their own scrape config and alerts** in their own charts. No central `prometheus.yml` that every team has to send a PR against. Our chart already ships a `ServiceMonitor` ([§10.1](phase-1-the-application.md#101-one-chart-two-workloads)) — this is what makes it work.

### 13.2 Install

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update
helm search repo prometheus-community/kube-prometheus-stack --versions | head -3
```

Pin whatever the top line reports; `82.14.1` is known-good.

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

> **`serviceMonitorSelectorNilUsesHelmValues: false` is the single most useful line in that file.** With the default (`true`), Prometheus only picks up ServiceMonitors labelled `release: monitoring`. Our chart sets that label deliberately — but any chart that doesn't will be silently ignored, with no error anywhere. Turning the restriction off trades a little namespace hygiene for not losing an afternoon.

Grafana is now at <http://grafana.localtest.me> (`admin` / `admin`).

### 13.3 Confirm your app is being scraped

The CRDs exist now, so turn the monitor on. **Which one depends on where you are in the build**, and
right now there is no service mesh, so Prometheus can talk to your pods directly:

```bash
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
> [Phase 4](phase-4-service-mesh.md) turns on STRICT mTLS and Prometheus loses the ability to speak
> plaintext to anything. `podMonitor` is the replacement for that world, and
> [§9.6](phase-4-service-mesh.md#96-the-metrics-problem-you-just-created) is where you switch. Turning
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

Everything in [§9](phase-4-service-mesh.md#9-istio-the-service-mesh) is invisible. mTLS either works or it doesn't; an `AuthorizationPolicy` either matches or it doesn't; and when it doesn't, the symptom is a 403 in a log somewhere. Kiali reads the same Prometheus you just installed plus Istio's configuration, and draws the answer.

It goes here, not in §9, for one reason: **without Prometheus there is no graph.** Kiali's topology is derived entirely from `istio_requests_total` — the metric the merged endpoint in [§9.6](phase-4-service-mesh.md#96-the-metrics-problem-you-just-created) gets you. Install Kiali before Prometheus and you get an empty page with no error.

```bash
helm repo add kiali https://kiali.org/helm-charts
helm repo update

helm install kiali-server kiali/kiali-server \
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

**Next: [Phase 3 — Delivery](phase-3-delivery.md).** With a dashboard in front of you, automating
deploys stops being reckless — you will be able to see what each one did.

[← All phases](README.md) · [← Phase 1 — The application, running](phase-1-the-application.md) · [Phase 3 — Delivery: git as the deploy button →](phase-3-delivery.md)

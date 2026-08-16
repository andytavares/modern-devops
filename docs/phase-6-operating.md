# Phase 6 — Operating it, and taking it down

[← All phases](README.md) · [← Phase 7 — One build system, many languages](phase-7-polyglot-monorepo.md) · [Appendices →](appendices.md)

> **Where this starts:** a platform that works when nothing is wrong.
> **Where it ends:** a platform you have personally broken in six specific ways and watched recover.

A green dashboard proves the happy path. It proves nothing about the failure paths, and the failure
paths are the entire reason for most of what you built. So break it on purpose, while you are calm
and nothing is at stake.

Then tear it down, because a lab you cannot cheaply destroy is a lab you will start being careful
around — and being careful is the opposite of what this is for.

---

## 15. End to end

Everything below exercises the whole platform at once. When a step surprises you, the phase that
built that piece is where to go back to:

| What you're exercising | Built in |
|---|---|
| The request reaching the cluster at all | [Phase 0](phase-0-foundations.md) — kind port mappings + ingress-nginx |
| `order-api` → S3 → Kafka → `order-worker` → DynamoDB | [Phase 1](phase-1-the-application.md) |
| Seeing the order count move | [Phase 2](phase-2-observability.md) |
| A code change reaching the cluster without you | [Phase 3](phase-3-delivery.md) |
| The call being refused when identity is wrong | [Phase 4](phase-4-service-mesh.md) |
| Adding a service without editing CI or the chart | [Phase 5](phase-5-developer-portal.md) |
| One command building three languages, and the canary between two pricing versions | [Phase 7](phase-7-polyglot-monorepo.md) |

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
([§18.1](phase-7-polyglot-monorepo.md#181-the-contract)) — it is what makes the canary visible.

### 15.2 Follow it through every hop

**S3 (Floci)** — from inside the mesh, since §9.4 turned on STRICT mTLS ([§6.4](phase-1-the-application.md#64-reaching-floci-from-your-laptop) explains why `port-forward` no longer works):

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
`tests/test_openapi_spec.py` fails the build ([§19.6](phase-7-polyglot-monorepo.md#196-two-checks-nothing-else-would-catch)):

```bash
pants run services/order-api:dump-openapi > services/order-api/openapi.json

git add services/order-api/order_api/main.py services/order-api/openapi.json
git commit -m "feat(order-api): return service version in the order response"
git push
```

Now watch, in order:

1. **Buildkite** — the pipeline starts within seconds (GitHub webhook). One `lint · typecheck · test · package` step for every language ([§19.5](phase-7-polyglot-monorepo.md#195-one-ci-step-instead-of-two)), then the Buildah builds in parallel, then the tag bump.
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

`selfHeal: true` reconciles it away within ~20 seconds. Argo CD logs the correction. This is what "git is the source of truth" actually means operationally, and it's why the escape hatch in [§11.4](phase-3-delivery.md#114-the-app-of-apps) matters during incidents.

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

That pod is in the mesh, holds a valid certificate, and is still refused — because its identity is `sa/default`, not one of the two principals in [§9.5](phase-4-service-mesh.md#95-authorization-deny-by-default-then-allow-the-paths-that-exist). Compare with a stolen-IP attack: there is nothing to steal. Then look at the same request in Kiali's graph as a red edge into `floci`, which is how you'd find it if you weren't the one who caused it.

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

**And count what still needs a human.** The PR needs a reviewer. The new service has no Kafka topic, no secret, no dashboard of its own, and its `catalog-info.yaml` only reaches Backstage once the root catalog file references it ([§14.7](phase-5-developer-portal.md#147-paved-path-2--infrastructure)). A paved path is a floor, not a ceiling — the moment you pretend it's a ceiling, teams route around it and you're back to copy-paste with extra steps.

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

If you want to keep going, [Appendix C](appendices.md#appendix-c--what-this-deliberately-left-out) is
the honest list of what this platform does not do, roughly in the order the omissions will start to
hurt.

[← All phases](README.md) · [← Phase 7 — One build system, many languages](phase-7-polyglot-monorepo.md) · [Appendices →](appendices.md)

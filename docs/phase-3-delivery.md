# Phase 3 — Delivery: git as the deploy button

[← All phases](README.md) · [← Phase 2 — Seeing what it does](phase-2-observability.md) · [Phase 4 — Identity between services →](phase-4-service-mesh.md)

> **Where this starts:** an application you deploy by typing `helm upgrade` and remembering a tag.
> **Where it ends:** `git push` to `main` builds, pushes and deploys, and the cluster holds no
> credentials for anything.

Two halves that are frequently conflated and should not be:

- **Argo CD** pulls. It watches git and makes the cluster match it. It takes ownership of the release
  you installed by hand in Phase 1 — you will watch that handover happen.
- **Buildkite** builds. It never touches the cluster. Its total privilege is *push a commit*.

That split is the whole security argument. If CI is compromised, the attacker gets a reviewable,
revertible commit — not cluster admin. Compare that with a pipeline holding a kubeconfig.

---

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

> **First, hand over what you installed by hand.** In [§10.5](phase-1-the-application.md#105-install-it)
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
3. Inside `local`, go to **Queues** and confirm a queue named `default` exists. Create a queue named **`kubernetes`** — our agent stack advertises this tag, and steps target it. On the *"Select your agent infrastructure"* step you **must** choose **Self-hosted**, not Hosted.
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

> [!warning] **Self-hosted vs Hosted is the single most expensive click in this tutorial.**
> Buildkite's New Queue form defaults to **Hosted**, and a hosted queue runs jobs on Buildkite's own
> machines — not your kind cluster. Everything still *looks* right: the queue says `Connected`, your
> `agent-stack-k8s` pod is `Running`, and builds start. But the controller logs
> `job tags do not match expected tags in configuration, skipping` on a loop, because a hosted agent
> tags itself `namespace-experiments=docker.builder=local` and your controller only advertises
> `queue=kubernetes`. Buildkite's hosted agent then runs the job instead, hits the `kubernetes`
> plugin — which `agent-stack-k8s` *interprets* rather than downloads — tries to `git clone`
> `buildkite-plugins/kubernetes-buildkite-plugin`, and dies with:
>
> ```
> Can't issue repository access token: The repo you've requested a token for
> (buildkite-plugins/kubernetes-buildkite-plugin) is in a different org to the
> repo for this job (<you>/modern-devops).
> 🚨 Error: failed to checkout plugin kubernetes: exit status 128
> ```
>
> A Git authentication error about a repository you have never heard of is what a wrong queue type
> looks like. The infrastructure choice **cannot be changed after creation** — the queue's Settings
> page offers only description, capacity and *Delete Queue* — so getting it wrong means deleting the
> queue and making a new one. Check it before you click Create.

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

The build pushes images to Nexus. Source that credential from OpenBao, in the `buildkite` namespace.

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
```

```bash
kubectl apply -f deploy/platform/buildkite-secrets.yaml
kubectl -n buildkite get externalsecret nexus-push
kubectl -n buildkite get secret nexus-push -o jsonpath='{.data.config\.json}' | base64 -d | jq .
```

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

You should see `order-api` and `order-worker` pods Running, on images tagged with your commit SHA:

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

**Next: [Phase 4 — Identity between services](phase-4-service-mesh.md).**

[← All phases](README.md) · [← Phase 2 — Seeing what it does](phase-2-observability.md) · [Phase 4 — Identity between services →](phase-4-service-mesh.md)

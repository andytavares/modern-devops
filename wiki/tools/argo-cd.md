---
type: tool
tags: [cd, gitops]
role: Continuous delivery — the cluster pulls from git
version: v3.4.7
docs: https://argo-cd.readthedocs.io/en/stable/
date_added: 2026-08-15
date_updated: 2026-08-16
status: in-use
---

# Argo CD

> [!info] One-liner
> A controller that continuously reconciles the cluster against a git repo — CI never needs cluster credentials.

## What it is

A GitOps engine. An **`Application`** names a repo, a path, a revision and a destination; the
controller renders it (Helm, Kustomize or plain YAML) and applies it, then keeps applying it. Drift
is detected and, with `selfHeal`, reverted.

The security consequence is the headline: **delivery is a pull, not a push.** CI's total privilege
becomes "push a commit". If CI is compromised, the attacker gets a reviewable, revertible commit —
not cluster admin. Compare `helm upgrade` running in a pipeline with a kubeconfig.

## What it does here

App-of-apps (§11.4): a root `Application` points at `deploy/argocd/apps/`, which declares:

| Application | Path | Sync policy |
|---|---|---|
| `order-platform` | `deploy/charts/order-platform` + `env/local/values.yaml` | `prune: true`, `selfHeal: true` |
| `platform` | `deploy/platform` (recursive) | `prune: false`, `selfHeal: true` |

The `platform` app recursing `deploy/platform` is what makes the [[backstage]] infrastructure paved
path work with no extra wiring — a new manifest in a subdirectory is picked up automatically (§14.7).

## Key concepts

- **`prune` is per-Application and deliberate** (§11.4). `true` on workloads makes git authoritative;
  `false` on shared platform infra, because a bad rebase that drops a file should not delete your
  Kafka cluster and its PVCs. Different blast radius, different setting.
- **`selfHeal: true` makes `kubectl edit` temporary.** Correct default, infuriating during an
  incident. Escape hatch: `argocd app set <app> --sync-policy none`, consciously.
- **Polling is a fallback, not the design.** Default 3-minute interval; the production answer is a
  webhook to `argocd-server/api/webhook`, which needs an inbound URL a laptop doesn't have.
- `Degraded` on a nonexistent image tag is Argo faithfully reporting that desired state is
  unachievable — not a bug.

## Gotchas

- Argo would otherwise try to own the Ingress it is served from; the tutorial excludes
  `argocd-ingress.yaml` to avoid a self-referential sync.
- The initial admin secret is a static credential with no expiry — delete it after changing the password.

> [!warning] Endless login redirect on `http://` — hit 2026-08-15
> `argocd-server` runs in default TLS mode (no `--insecure`, `server.insecure` unset in
> `argocd-cmd-params-cm`) and the Ingress sets `backend-protocol: HTTPS`, so the `argocd.token` cookie
> carries the `Secure` flag. Over plain `http://` the login page renders and the password is accepted,
> but the browser **silently discards** a `Secure` cookie — the next request is unauthenticated and
> bounces to `/login`, forever, with nothing logged in the browser or in
> `kubectl logs deploy/argocd-server`. **Always use `https://argocd.localtest.me`** and accept the
> self-signed certificate.

> [!warning] An Application syncs as a unit — one bad resource strands all of them
> Hit 2026-08-16. `order-platform` rendered a `PodMonitor` before kube-prometheus-stack had installed
> the `monitoring.coreos.com` CRDs (§13.2). Argo CD does **not** skip the unrenderable resource; the
> sync fails as a whole and every *other* resource stays `Missing`:
>
> ```
> Deployment shop/order-api      OutOfSync  Missing
> Deployment shop/order-worker   OutOfSync  Missing
> Service    shop/order-api      OutOfSync  Missing
> PodMonitor shop/order-platform OutOfSync  Missing  The Kubernetes API could not find
>                                                    monitoring.coreos.com/PodMonitor …
> ```
>
> `kubectl -n shop get pods` returns nothing, which reads like a scheduling or image-pull problem and
> is neither. `status.operationState` says `one or more synchronization tasks are not valid`, and only
> the *offending* resource carries a message — so read every row, not just the failing one.
>
> The general rule: **CRD-dependent resources must be gated behind a values flag until the operator
> that owns the CRD is installed.** Ours is `podMonitor.enabled`, defaulted `false` and flipped in
> §13.3. `SkipDryRunOnMissingResource=true` is the other lever, but it defers the error to apply time
> rather than removing the ordering problem. See [[prometheus]].

> [!warning] `PermissionDenied` usually means "does not exist"
> `argocd app get <name>` returns `rpc error: code = PermissionDenied` for an application that is
> simply absent — deliberate, so the API doesn't leak which app names exist. Check
> `argocd account get-user-info` before assuming an RBAC problem; if it says
> `Logged In: true, Username: admin`, the token is fine and the app is missing.

> [!warning] Deleting an Application cascades — and can wedge
> The `resources-finalizer.argocd.argoproj.io` finalizer deletes **every resource the Application
> manages**. If any managed object cannot finish deleting, the Application sits in `deleting` forever,
> logging `1 objects remaining for deletion` on a loop, and `argocd app sync` refuses with
> `FailedPrecondition: application is deleting`. Seen 2026-08-15: an app-of-apps hung ~80 minutes on a
> single [[apache-kafka]] `KafkaTopic` whose finalizer could never be satisfied — see [[strimzi]].
> Find the blocker with
> `kubectl -n argocd get app <name> -o jsonpath='{.status.resources[*]}'`, then clear the dead
> finalizer. Re-applying `root.yaml` afterwards rebuilt the whole platform from git in under a minute.

## Official docs

- Docs: https://argo-cd.readthedocs.io/en/stable/
- Application spec: https://argo-cd.readthedocs.io/en/stable/operator-manual/application.yaml
- App-of-apps pattern: https://argo-cd.readthedocs.io/en/stable/operator-manual/cluster-bootstrapping/

> [!tip] Related
> [[gitops]], [[helm]], [[buildkite]], [[immutable-image-tags]], [[backstage]]

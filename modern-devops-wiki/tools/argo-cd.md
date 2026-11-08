---
type: tool
tags: [delivery, gitops, operator]
role: pull-based GitOps — CI never touches the cluster
version: v3.4.7
docs: https://argo-cd.readthedocs.io/en/stable/
date_added: 2026-08-17
date_updated: 2026-08-23
status: in-use
---

# Argo CD

> [!info] One-liner
> A controller in the cluster that watches git and converges the cluster onto it. Its existence is why [[buildkite]]'s total privilege is "push a commit".

## Why pull beats push (§11.1)

1. **Credentials.** CI never gets cluster admin. Your build system is internet-facing and runs
   arbitrary code from pull requests.
2. **Drift.** Argo continuously compares live state to git and reports `OutOfSync`. Push-based CD is
   blind between deploys — an emergency `kubectl edit` is invisible until the next release silently
   reverts it.
3. **Disaster recovery.** Desired state is a git repo. Rebuilding is "point a new Argo CD at it".
4. **Audit.** Every change is a commit with an author and a review.

**The cost is real and teams that dislike GitOps dislike exactly this:** deploys are asynchronous. CI
finishes with "commit pushed", not "deployed", and a failed deploy surfaces in a different tool than
the build that caused it. See [[gitops]].

## The app-of-apps (§11.4)

`deploy/argocd/root.yaml` points at `deploy/argocd/apps/`, which holds two Applications:

| Application | Source | Prune | Why |
|---|---|---|---|
| `order-platform` | `deploy/charts/order-platform` + `deploy/env/local/values.yaml` | **true** | Application workloads; delete a manifest, the object goes |
| `platform` | `deploy/platform` (recursive) | **false** | Shared infrastructure. A bad rebase dropping a file would delete your [[apache-kafka]] cluster **and its PVCs** |

Different blast radius, different setting. Decide it per-Application, deliberately.

`platform` excludes `argocd-ingress.yaml` — Argo would otherwise try to own the Ingress it is being
served from.

**First, hand over what you installed by hand.** §11.4 has you `helm uninstall order-platform` before
bootstrapping. Two owners for one Deployment is a fight nobody wins. Deleting a working deployment to
let a controller recreate it feels wrong the first time — and if Argo cannot recreate it, the repo was
never a truthful description of your platform, which is much better to learn now than during an
incident.

## Configuration that is not obvious

**`kubectl apply --server-side --force-conflicts` to install.** Argo's CRDs exceed the 262 KB
annotation limit client-side apply uses for last-applied config, and a client-side apply fails with a
confusing metadata error. Pin the version — `stable` moves under you and would silently upgrade Argo CD
mid-incident.

**`ServerSideDiff=true` on the `platform` Application.** The [[external-secrets-operator]] CRD defaults
a pile of fields the API server injects that are not in git; a client-side diff reads them as drift and
parks the Application on `OutOfSync` forever, while `kubectl diff` reports no difference at all.

**Every CRD an Application references must already exist when it syncs.** Argo does not skip a resource
whose CRD is missing — it fails the **entire** Application, so one unrecognised `PodMonitor` leaves
every workload in `shop` reported as `Missing`. That is why the chart's `serviceMonitor` and
`podMonitor` toggles both default to `false` until §13.2 installs the `monitoring.coreos.com` CRDs.
**Operator first, custom resources second.**

> [!warning] `https://argocd.localtest.me`, never `http://`
> `argocd-server` runs in default TLS mode and the Ingress sets `backend-protocol: HTTPS`, so Argo
> marks its `argocd.token` cookie `Secure`. Over plain http the login page renders, the password is
> accepted, the browser **silently discards the cookie**, and you bounce back to `/login` forever —
> with no error in the browser and none in `kubectl logs deploy/argocd-server`. An endless login
> redirect on http is this and nothing else (§11.2).

> [!warning] `Synced` can be a stale cache
> Argo has been observed reporting `Synced` against a revision it had not applied — a workload in
> `CrashLoopBackOff` on an old image tag while `values.yaml` at the synced revision named a newer one,
> with `selfHeal: true` and a `Succeeded` sync operation 52 minutes stale. Suspect this when `Synced`
> and `Degraded` appear together and the rendered manifest in git plainly differs from the live object.
> Fix: `kubectl -n argocd annotate app <name> argocd.argoproj.io/refresh=hard --overwrite`
> (Appendix B).

## `helm upgrade` by hand stops working the moment Argo owns the release, and the error is the good outcome

Observed 2026-08-23 at §9.6, running the tutorial's own instruction:

```
Error: UPGRADE FAILED: conflict occurred while applying object shop/order-api
apps/v1, Kind=Deployment: Apply failed with 3 conflicts: conflicts with "argocd-controller":
- .spec.template.metadata.annotations.checksum/config
- .spec.template.spec.containers[name="order-api"].image
- .spec.template.spec.containers[name="order-api"].env[name="SERVICE_VERSION"].value
```

The mechanism: this Application syncs with `ServerSideApply=true` (§11.4), so the API server records
`argocd-controller` in `metadata.managedFields` as the owner of every field Argo sets. Helm 3.18+ also
applies server-side, so a hand-run `helm upgrade` arrives as a **different field manager claiming
fields someone else owns**, and [server-side
apply](https://kubernetes.io/docs/reference/using-api/server-side-apply/#conflicts) refuses rather
than picking a winner.

> [!warning] Forcing it is wrong twice, and the second reason is the one that hurts
> `--force-conflicts` (kubectl) or `--take-ownership` (Helm) will push it through. That steals the
> fields from `argocd-controller` — and then `selfHeal: true` reverts your change on the next
> reconcile anyway. Net result: a cluster that disagrees with git, a change that disappeared minutes
> after you made it, and nothing in any log tied to the thing you actually did. **The conflict error
> is two controllers being stopped from fighting; silence would have been the bug.**

The three conflicting fields are worth reading, because they name exactly what Argo owns and you do
not: the image tag (rewritten by [[buildkite]] into `deploy/env/local/values.yaml`), `SERVICE_VERSION`
(same rewrite), and `checksum/config` (the pod-restart annotation the chart computes from values).
Every one of them is a value the delivery path sets. After §11 the deploy button is `git push`, and
`argocd app sync <app>` if you will not wait for the poll — that is Argo applying git, not you
applying your laptop. See [[gitops]].

## `selfHeal: true` means `kubectl edit` is temporary

Argo reverts your change within ~20 seconds. Correct default, and it will infuriate you the first time
you are debugging live. The escape hatch is `argocd app set <app> --sync-policy none` for the duration
of the incident — done consciously, rather than fighting the controller (§11.4, §15.4).

## Latency

Polling is 3 minutes by default. The production fix is **not** a shorter interval — it is a webhook
from GitHub to `argocd-server/api/webhook`, making syncs event-driven. That needs an inbound URL a
laptop does not have, so this platform polls. Know that polling is the fallback, not the design.

## Rollback

`git revert` the deploy commit and push — the audit trail records who and when. Or
`argocd app rollback <id>`, which is faster in an incident and puts the cluster out of sync with git
until you follow up with the revert. **Know which one you are doing** (§15.4).

## Related

[[gitops]] · [[reconciliation]] · [[buildkite]] · [[helm]] · [[order-platform]] · [[immutable-image-tags]] · [[strimzi]]

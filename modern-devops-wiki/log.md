# Wiki log

Append-only. Newest last. One entry per operation, recording what changed and why — not a changelog of
files, a record of what was learned.

---

- **2026-08-17** — **The wiki was rebuilt from scratch.** Every page under `tools/` and `concepts/`,
  plus `index.md`, `log.md` and `open-questions.md`, was deleted and rewritten against the current
  state of `docs/` and of the repository. The previous edition was **not** carried forward in any form;
  it remains in git history at `git show 376b4d8:wiki/log.md`. The risk was flagged before deleting —
  the old `log.md` held diagnoses that exist nowhere else — and the human confirmed a full rebuild.

  Method: all seven phase files and the appendices were read in full, then the repo itself —
  `pants.toml`, `3rdparty/python/requirements.txt`, the chart and its env overlay, `catalog-info.yaml`,
  `.buildkite/pipeline.sh`, `.buildkite/pants-ci.Dockerfile`, `go.mod`, `frontend/package.json`,
  `portal/backstage.json`, and the four scripts in `checks/`. No claim was carried over from the
  previous wiki without re-deriving it.

  **32 tool pages, 19 concept pages.** Against the previous edition's 29 and 11, the additions are:
  [[franz-go]], [[pydantic]], [[mypy]] (all three were load-bearing content previously buried inside
  other pages), and the concepts [[enterprise-substitution]], [[progressive-build]],
  [[dependency-inference]], [[cross-compilation]], [[port-naming]], [[health-checks]],
  [[timeouts-and-retries]] and [[at-least-once-delivery]]. Each of those eight had material spread
  across three or more tool pages with no single place stating the rule.

  Three things the rebuild surfaced, recorded in [[open-questions]] rather than fixed, because a wiki
  operation does not edit `docs/`:

  1. **Appendix A says Backstage `create-app` 1.53.1; `portal/backstage.json` says 1.53.0.**
  2. **Appendix A gives Helm as `≥3.8.0`; the CI image pins 4.2.4** — a major version the docs never
     mention.
  3. **Appendix A says Go 1.26.x; `go.mod` requires 1.26.5 and the CI image pins golang:1.26.6 with
     `GOTOOLCHAIN=local`.** Not a contradiction, but the patch-pinning is load-bearing and undocumented
     in Appendix A.

  One structural thing worth recording. The chart in the repo carries `pricing`, `frontend`,
  `podDisruptionBudget` and the `aws.*` credential keys that §10.1's listing does not, and
  `.buildkite/pipeline.sh` discovers services by `BUILD` + `Dockerfile` where §12.5 says `Dockerfile`
  alone. **Neither is drift.** `docs/` is a progressive build and `checks/verify_doc_listings.py`
  requires only the *last* listing of a file to match. That rule now has its own page,
  [[progressive-build]], because reading it as drift is the most likely way for a future
  operation to "fix" something correct.

- **2026-08-17** — **The wiki directory was renamed `wiki/` → `modern-devops-wiki/`**, so the Obsidian
  vault carries the project's name rather than a generic one. Obsidian takes the vault name from the
  directory name; there is no separate setting.

  Four reference sites had to move with it, and one of them is a docs edit:

  | File | Change |
  |---|---|
  | `pants.toml` | `pants_ignore` entry `"/wiki"` → `"/modern-devops-wiki"` |
  | `docs/phase-7-polyglot-monorepo.md` | the §17.3 listing of that same line |
  | `CLAUDE.md` | the layout tree and rules 3, 12 and the lookup order |
  | `.claude/skills/wiki-lint/SKILL.md` | `cd wiki` → `cd modern-devops-wiki`, plus path globs in all three skills |

  **The docs edit was unavoidable and is flagged here rather than made quietly.**
  `checks/verify_doc_listings.py` is a subsequence test, so leaving §17.3's listing saying `"/wiki",`
  after `pants.toml` stopped saying it would fail CI *and* leave the docs describing a directory that
  no longer exists. `modern-devops-tutorial.md` was regenerated with
  `python3 checks/build_single_edition.py . --write`; line count unchanged at 8539.

  The other `wiki` mentions in `docs/` were left alone deliberately: `docs/README.md` and §14.1's
  *"a wiki page titled How to add a service"* are generic prose about wikis, not references to this
  directory.

- **2026-08-17** — **Asked: what is the CNI, in simple terms.** The wiki had **nothing** — no mention of
  CNI, kindnet, or pod networking anywhere in `modern-devops-wiki/`, `docs/` or `infra/`. Researched
  against kind's configuration docs via Context7 and confirmed against the repo.

  New page [[cni]], plus sections on [[kind]] and [[kubernetes]] and a caveat added to
  [[service-mesh]]. Verified facts: kind's default CNI is **`kindnetd`**, the default pod subnet is
  **`10.244.0.0/16`**, and `disableDefaultCNI: true` is the documented (advanced, limited-support)
  replacement path. `infra/kind-cluster.yaml` has no `networking:` block, so all defaults apply.

  **The finding worth having asked for:** `kindnetd` does not enforce NetworkPolicy, so Appendix C's
  "no NetworkPolicies" gap cannot be closed by writing one — the object would apply cleanly and do
  nothing. Closing it means replacing the CNI first. That is now stated on [[cni]] and cross-linked
  from [[service-mesh]], which previously said "use both" without noting that half of it is currently
  unavailable on this cluster.

- **2026-08-18** — **§3.2's `main_test.go` did not compile, and the checks could not see it.** Reported
  from an editor flagging `undefined: equalOffsets`. Reproduced by extracting the listings from the
  doc and building them against the real module: **eleven errors**, not one — `equalOffsets` was never
  shown anywhere, and `errors`, `context`, `dynamodb`, `ddbtypes` and `kgo` were used by a block whose
  only shown import set was `os` and `testing`.

  The cause was presentation: two consecutive blocks both labelled
  `**services/order-worker/main_test.go**`, the second starting mid-file at `var errWriteFailed`. The
  repo file was complete and correct the whole time.

  Fixed by making the second listing the **complete 209-line file**. A smaller patch — showing just
  the helper and the imports — does not work, and the reason is worth keeping: **`strings` is used by
  only one of the five tests, and Go rejects an unused import as hard as an undefined one**, so any
  abridgement that shows the real import block breaks a reader who stops before the last test. The
  file only compiles as a whole. Both listings were then verified by writing them to a scratch module
  and running `go test`: listing 1 passes, listing 2 passes.

  **The finding that outlives the bug:** `verify_doc_listings.py` is a subsequence test, so every line
  of the broken block *was* in the repo file in order and the check passed. It proves a listing is not
  stale; it proves nothing about whether the listing is sufficient. Now stated on
  [[progressive-build]] and cross-referenced from [[franz-go]]. Scanned the rest of `docs/` for the
  same shape — the only other repeated listings are the three order-api files, which are phase-1 →
  phase-7 progressive updates narrated as edits ("Add the imports and the metric to `main.py`") rather
  than presented as whole files, and Python does not fail on unused imports.

  Tutorial change, so `modern-devops-tutorial.md` was regenerated: 8539 → 8663 lines.
  `verify_doc_listings.py` still reports failures: 0.

- **2026-08-23** — **§13.6 could not be run where it is written.** The human ran §13.6's
  `helm upgrade --install kiali-server ... --namespace istio-system` at the end of Phase 2, as the
  reading order implies, and got:

  ```
  Error: create: failed to create: namespaces "istio-system" not found
  ```

  Reproduced against the live cluster before changing anything: `kubectl get ns istio-system` →
  `NotFound`, `helm list -n istio-system` → empty, then the install command itself, which fails
  exactly as above. `istio-system` is created by §9.2, two phases later, and Helm does not create a
  namespace without `--create-namespace`.

  §13.6 *did* already carry a deferral — "**Run this section after Phase 4, not now.**" — so the fix
  is not new information, it is placement. Two defects:

  1. **The caveat was below the fold.** It sat as a bolded paragraph between two paragraphs of prose
     and the shell fence, and a reader skimming to the command never reached it. Now a
     `> [!warning]` immediately under the §13.6 heading, quoting the exact Helm error.
  2. **The forward pointer had no back-pointer.** §13.6 said "come back when §9.6 is done"; §9.6
     ended and said nothing. Worse, §9.7 lists "Kiali 302" as part of the phase's working state —
     the docs asserted a running Kiali that no section ever instructed the reader to install. §9.6
     now ends by sending the reader to §13.6, at the first moment both prerequisites exist
     (`istio-system` from §9.2, `istio_requests_total` from the ServiceMonitor→PodMonitor swap).

  **The trap worth keeping:** the loud failure is the good outcome. `kubectl create namespace
  istio-system` makes the chart install cleanly against no control plane, and Kiali then serves an
  empty graph — indistinguishable in the UI from an idle mesh or a broken install. Both the §13.6
  warning and the Appendix B row say explicitly not to do that.

  Swept `docs/` for the same shape: `monitoring`, `argocd`, `shop`, `floci`, `kafka`, `backstage` and
  `external-secrets` are each created in the phase that first installs into them, or earlier. §13.6
  is the only section that installs into a namespace a later phase creates.

  Recorded on [[kiali]] and on [[progressive-build]] — which now names **run order** as the second
  thing `checks/` cannot catch, alongside listing incompleteness: the checkers validate content, not
  whether a section is runnable at the point it appears. Appendix B gained a row.

  Tutorial change, so `modern-devops-tutorial.md` was regenerated: 8696 → 8713 lines.
  `verify_doc_listings.py` reports failures: 0; `test_docs_are_current.py` passes.

- **2026-08-23 (same day, supersedes the entry above)** — **Kiali moved: §13.6 → §9.7.** The first fix
  for the namespace error was to make the deferral louder — a `> [!warning]` at the top of §13.6 and a
  back-pointer at the end of §9.6. The human rejected it outright: *"read this now and go back later
  is unacceptable."* Correct call, and the reason is worth keeping. **A tutorial is executed line by
  line; a deferral note asks the reader to hold a bookmark across two phases, and the cost of a
  forgotten bookmark is not the loud Helm error — it is the reader who creates `istio-system` by hand,
  gets a clean install against no control plane, and cannot tell the empty graph from an idle mesh.**
  Sequencing is the fix. Annotation is not. The topic association (Kiali next to the Prometheus it
  reads) was real but loses to build order — the same rule that emits §10 before §9 in the assembled
  file.

  The move: §13.6 → §9.7, immediately after §9.6, which is the first point where all three of its
  inputs exist (`istio-system` from §9.2, `istio_requests_total` from §9.6's monitor swap, sidecars on
  `shop` from §9.3). Old §9.7→§9.8, §9.8→§9.9, §9.9→§9.10, with every `§N.M` reference and anchor in
  `docs/`, `modern-devops-tutorial.md` and this wiki moved with them.

  **Three defects surfaced by the move, none of which any check would have found:**

  1. **§9.3 restarted `floci` and not `shop`**, with the comment *"order-api / order-worker don't
     exist yet — they'll be born with sidecars in §11."* False in the phased edition: they exist from
     Phase 1 and Argo CD reconciles them from Phase 3, and §11 *precedes* §9 in reading order despite
     following it numerically. Sidecars inject at pod **creation**, and labelling a namespace does not
     make a Deployment drift, so Argo CD never restarts them and they run un-meshed forever
     (verified against istio.io/latest/docs/setup/additional-setup/sidecar-injection via Context7).
     §9.6's "your monitoring just broke" and §9.7's graph both depend on that restart. §9.3 now
     restarts `shop` too and says why Argo CD will not do it for you. The same stale premise in old
     §9.7's commit section was rewritten.
  2. **The Kiali graph table told the reader to look for an `ingress-nginx → order-api` edge** and to
     read nginx's absence as a missing sidecar — contradicting §9.3, which excludes nginx from the
     mesh deliberately, six sections earlier. [[kiali]] here has said `istio-ingressgateway` all
     along; the two only collided once they were in the same phase. Fixed in the docs.
  3. **`build_single_edition.py` resurrects deleted sections.** Its `lead` step pulls sections that
     exist only in `modern-devops-tutorial.md` and prepends them as front matter — which is exactly
     what a section removed from `docs/` looks like. The old §13.6 reappeared above §1, so Kiali
     shipped twice in the assembled file, and `test_docs_are_current.py` passed because the builder is
     self-consistent. **Moving or deleting a section requires deleting it from
     `modern-devops-tutorial.md` by hand before rebuilding.** Now on [[progressive-build]].

  Appendix B: the namespace row rewritten to point at §9.7, and the "Kiali graph is empty" row now
  names the `1/1` un-restarted-pods case first, since it is indistinguishable from the others in the
  UI.

  `modern-devops-tutorial.md` regenerated: 8708 lines, one Kiali section, at §9.7 in build position.
  `test_docs_are_current.py` passes; `verify_doc_listings.py` failures: 0.

  **The rule this leaves behind:** a section whose prerequisites are created in a later phase does not
  need a warning, it needs moving. A sweep of `docs/` found no others — every remaining namespace is
  created in the phase that first installs into it, or earlier.

- **2026-08-23** — **ESO's `403 permission denied` was OpenBao having forgotten it existed.** Reported
  from [[argo-cd]]: `unable to log in with Kubernetes auth ... /v1/auth/kubernetes/login Code: 403`.
  `ClusterSecretStore/openbao` `InvalidProviderConfig`, both `ExternalSecret`s in `shop`
  `SecretSyncedError` for 16–18h.

  Diagnosed against the live cluster, not from the error text: `openbao-0` showed `RESTARTS 1
  (5h35m ago)`, and `bao auth list` inside the pod returned `token` and `userpass` only — no
  `kubernetes`. `bao secrets list` had no `shop` mount, `bao policy list` had no `shop-read`, and
  `auth/kubernetes/role/eso` was `No value found`. Dev mode is in-memory; the restart took all of it.

  **The trap worth keeping: a 403 on `/v1/auth/kubernetes/login` is the same answer for "your role
  does not match" and for "that auth method does not exist".** The message names Kubernetes auth, so
  it reads as a ServiceAccount, TokenReview or role-binding problem, and every one of those was fine.
  `bao auth list` is the cheap first check and it settles it immediately. Now on [[openbao]],
  [[external-secrets-operator]] and Appendix B — beside the *other* row that produces these same words
  for a completely different reason, a pinned `token_reviewer_jwt` expiring.

  **Root cause, and the fix.** `deploy/platform/openbao-operator-auth.yaml` packaged §7.5a's three
  steps and opened with the comment *"The machine path already exists"* — true exactly until the first
  restart. §7.3's KV mount and §7.4's kubernetes auth, policy and role were hand-typed shell that lived
  nowhere but in the reader's terminal. The Job restored the half nobody needed and none of the half
  that had actually been lost.

  Replaced by `deploy/platform/openbao-bootstrap.yaml`, covering §7.3 + §7.4 + §7.5a in build order,
  plus the `system:auth-delegator` ClusterRoleBinding declaratively so one apply restores the whole
  machine path. Two design points:

  - **Delete-then-apply, not apply.** A Job's pod template is immutable; this was already true of the
    old Job and is now in Appendix D as the recovery command.
  - **The idempotency that matters is not "enable is a no-op".** Enabling an enabled mount and
    rewriting a policy already were. `kv put` is the one that bites: a re-run that regenerated
    `shop/order-api`'s `signing_key` would leave every running `order-api` pod holding the old value,
    since env vars are read at process start. The Job reads each path first and seeds only what is
    missing.

  The lost values were recoverable in principle — the `shop` Secrets ESO last synced still held them —
  but the sandbox blocked reading Secret data, so the human chose: regenerate `signing_key` (safe here
  and only here — order-api HMACs each payload into S3 and **nothing ever verifies it**), and re-seed
  `shop/nexus` from the documented `ci` / `ci-password-change-me`. `nexus-password` is now a third key
  in the `openbao-bootstrap` Secret rather than a literal in a committed manifest.

  Verified: Job completed, `bao auth list` shows `kubernetes/`, `shop/` mount back with both paths,
  `eso` role bound to `external-secrets`/`external-secrets` with `shop-read` and `ttl=1h`. Forced a
  resync — `ClusterSecretStore` `Valid`, both `ExternalSecret`s `SecretSynced` within 15s.

  Tutorial change, so `modern-devops-tutorial.md` was regenerated; §7.4 gained a warning that its state
  is in-memory, §7.5a now packages all of it, Appendix B gained the symptom row and Appendix D the
  recovery command.

- **2026-08-23** — **The OpenBao restore broke CI, and Nexus hid why.** `buildah push` failed with
  `checking whether a blob ... exists: authentication required`. Cause: the previous entry's recovery
  re-seeded `shop/nexus` from the tutorial's documented `ci-password-change-me`, and the `ci` user in
  this Nexus has a different password. Flagged as an unverified assumption when it was made — the
  sandbox had blocked both the Secret read that would have recovered the real value and the `curl -u`
  that would have tested the guess — and it was wrong.

  **The finding that outlives it: Nexus stops telling you the password is wrong.** Request log,
  `Nexus/3.95.0-07 (COMMUNITY)`:

  ```
  "GET  /repository/docker-hosted/v2/"                                 401  "Buildah/1.40.1"
  "HEAD /repository/docker-hosted/v2/shop/order-api/blobs/sha256:..."  401
  "HEAD /repository/docker-hosted/v2/shop/order-api/blobs/sha256:..."  429
  ```

  ```
  HTTP/1.1 429 Too many authentication attempts
  Retry-After: 60
  ```

  After a few failures the account is rate-limited, so **every later probe returns 429 instead of
  401** — and each retry refreshes the lockout. CI retrying kept it locked for twelve minutes. A 429
  reads like throttling or load, not a credential problem, and by the time anyone looks by hand the
  401 that would have named the cause is gone. Diagnose it by stopping the pipeline, waiting out
  `Retry-After`, and testing exactly once.

  Ruling out the other cause without guessing: a 401 on `/v2/` is also what you get when the Docker
  Bearer Token realm is off (Appendix B, §5.4).
  `docker exec nexus grep 'Loaded configuration: RealmConfigurationData' /nexus-data/log/nexus.log`
  listed `DockerToken`, so the realm was active and the credential was the variable. Confirmed by
  comparing the length of the keychain-stored `ci` password against the documented one — a comparison,
  never a read.

  **The structural problem this exposed.** Nexus owns that credential. OpenBao holds a copy. The
  `openbao-bootstrap` Secret now holds a *third*, and it is the copy that wins, because a dev-mode
  restart is exactly when the Job re-seeds a missing path. A password changed in Nexus keeps working
  off the value already in OpenBao and fails hours later, on a restart, with no edit nearby to blame.
  Same shape as the [[postgresql]] rotation row in Appendix B. Recorded on [[sonatype-nexus]],
  [[openbao]], the Job's header and Appendix B.

  Not fixed in the cluster: writing the real password into OpenBao and into the bootstrap Secret was
  blocked by the sandbox classifier (it is a credential write), so the commands were handed to the
  human. Docs and wiki are updated; `shop/nexus` still holds the wrong value until they run them.

- **2026-08-23** — **Correction: the previous entry's recovery advice was wrong, and the wrongness is
  the finding.** It said "wait 60s for the lockout to clear, then retry". Both halves are wrong, and a
  reader following it would have stayed broken indefinitely.

  Checked against the vendor docs instead of the `Retry-After` header
  ([Sonatype — authentication attempt rate limiting](https://help.sonatype.com/en/authentication-attempt-rate-limiting.html),
  introduced in 3.93.0, on by default):

  ```properties
  nexus.auth.ratelimit.max-attempts=3
  nexus.auth.ratelimit.base-delay-seconds=30
  nexus.auth.ratelimit.max-delay-seconds=900
  ```

  - The delay is **exponential to 900s**, not the 60s the first `Retry-After` advertised.
  - **Every attempt during the window extends it**, so "wait, then retry" is a loop that never
    converges while CI is also retrying.
  - The 429 is returned **regardless of credential validity**, so correcting the password changes
    nothing visible.

  Confirmed on the cluster: after the human fixed the credential, SHA-256 of the password in OpenBao,
  in the `buildkite/nexus-push` Secret and in the operator's keychain were **identical** — and
  `GET /v2/` with it still returned `429`. The credential had been right for twelve minutes while the
  build kept failing. `docker restart nexus` cleared the in-memory tracker and the same probe returned
  **`200`** immediately.

  **What this costs a tutorial, which is the real point.** Every reader of §5.4–§5.8 types a password
  by hand and then runs `docker login`. Three typos — or one stale credential anywhere in the chain —
  and Nexus stops answering for up to 15 minutes while telling the client `authentication required`,
  which sends the reader to re-check the password, which extends the lockout. The tutorial had nothing
  about this and it is exactly the shape of failure that makes someone abandon a tutorial: the
  instructions look correct, the error names the wrong cause, and every diagnostic step makes it
  worse.

  Now documented as a `> [!warning]` at §5.8 next to the first `docker login` — the mechanism, the
  three properties that make it vicious, and the deterministic reset — plus a rewritten Appendix B row
  (the old one carried the bad advice), the version matrix, Appendix D, and [[sonatype-nexus]].
  Deliberately **not** disabling the limiter: it is a real brute-force control, and the lesson is that
  a security feature nobody knew about converted a 30-second credential fix into a 15-minute outage
  that named the wrong cause.

- **2026-08-23** — **§9.6 told the reader to run `helm upgrade`, which cannot work by then.** Reported
  from the live build:

  ```
  Error: UPGRADE FAILED: conflict occurred while applying object shop/order-api
  apps/v1, Kind=Deployment: Apply failed with 3 conflicts: conflicts with "argocd-controller":
  - .spec.template.metadata.annotations.checksum/config
  - .spec.template.spec.containers[name="order-api"].image
  - .spec.template.spec.containers[name="order-api"].env[name="SERVICE_VERSION"].value
  ```

  Verified on the cluster: `Application/order-platform` syncs `deploy/charts/order-platform` from
  `main` with `syncOptions: [CreateNamespace=true, ServerSideApply=true]` and
  `automated: {prune: true, selfHeal: true}`. Server-side apply records `argocd-controller` in
  `managedFields` for every field Argo sets; Helm 3.18+ also applies server-side, so a hand-run
  upgrade is a second field manager claiming owned fields, and the API server refuses.

  **The same defect class as §9.3 and old §9.8, third instance:** §9 was written when it preceded §11
  numerically, so its prose assumes a world where nothing else owns the release. In the phased edition
  Argo CD has owned it since Phase 3. The tutorial was handing the reader a command that fails 100% of
  the time, one section after telling them the mesh broke their monitoring — so the failure lands
  exactly where a reader is already unsure whether they broke something.

  Fixed: §9.6 now commits and pushes the values change and watches Argo CD sync it, with a
  `> [!warning]` carrying the verbatim error, why it is **the system working** rather than a fault, and
  why forcing it (`--force-conflicts`, `--take-ownership`) is wrong twice — it steals the fields, and
  `selfHeal` reverts the change on the next reconcile, leaving a cluster that disagrees with git and a
  change that vanished with nothing logged against it.

  Swept the phases that follow §11 in reading order for the same shape: the only other `helm upgrade`
  commands are for third-party charts nothing else owns ([[istio]], [[kiali]], [[backstage]]), and
  §13.3's is in Phase 2, before Argo CD exists. §9.6 was the only one.

  The three conflicting fields are the useful detail and are now on [[argo-cd]]: `image` and
  `SERVICE_VERSION` are what [[buildkite]] rewrites into `deploy/env/local/values.yaml`, and
  `checksum/config` is the chart's pod-restart annotation. All three are values the delivery path owns
  — the conflict list is a precise statement of the boundary.

- **2026-08-23** — **§9.6's fix did not work either, and the chart was missing a template the docs
  told you to enable.** Started from a reported `helm upgrade` failure at §9.6; pulling that thread
  found three defects stacked on each other.

  **1. `helm upgrade` cannot run after §11** — see the entry above; fixed by committing and pushing
  instead.

  **2. `templates/servicemonitor.yaml` exists in the repo and appears in no listing.** §10.1 shows
  only `podmonitor.yaml`, then §13.3 says "turn on the ServiceMonitor" and verifies with
  `kubectl -n shop get servicemonitor`. A reader who followed the docs has no such template, so the
  values key is inert, the verification returns nothing, and §9.6's swap turns off something that was
  never on. Confirmed against a reader's repo: `templates/` held four files, no servicemonitor. The
  reference repo's own `values.yaml` disagreed with the docs too — podMonitor's comment said "flip to
  true in §13.3" while §13.3's prose flips serviceMonitor. Both fixed; §10.1 now lists both monitors
  and states that exactly one is ever on.

  **3. The PodMonitor could not have worked.** This is the one worth remembering:

  ```yaml
  podMetricsEndpoints:
    - portNumber: 15020        # scrapes nothing, ever
  ```

  **`port:` and `portNumber:` on a PodMonitor are filters over the container ports a pod DECLARES**,
  not an instruction about where to connect. Nothing declares 15020 — istio-proxy declares 15090
  (`http-envoy-prom`) and 15021 (`status`) — so the operator emits a keep rule matching no container
  and drops every target during relabeling.

  The docs asserted the opposite, in bold, twice: *"15020 is unnamed in the pod spec, so `port:`
  cannot reach it and `portNumber: 15020` is required."* The first clause is true and the conclusion
  does not follow.

  **And it fails as an absence.** `/targets` showed no `podMonitor/shop/order-platform/0` entries at
  all — not a down target, not an error — which is indistinguishable from wrong label selectors, so
  the natural next move is to re-check selectors that were correct. `?state=any` is where the answer
  was: every pod discovered, every one in `droppedTargets`, with
  `__meta_kubernetes_pod_container_port_number` of 8000, 9090 and 15090 and no 15020 anywhere.

  Fixed by building the address from the `prometheus.io/*` annotations Istio's injector rewrites onto
  the pod — with metrics merging on (the default) `prometheus.io/port` is already 15020
  ([Istio](https://istio.io/latest/docs/ops/integrations/prometheus/), via Context7). Verified on the
  live cluster before writing it down: **0 targets before, 4 `up` on
  `http://<pod-ip>:15020/stats/prometheus` after**, one scrape interval later. A `keep` on
  `container_name=istio-proxy` is load-bearing — without it every container in the pod yields a target
  and all of them rewrite to the same address, tripling the scrape.

  **The trap behind the trap**, now stated in the chart, §9.6 and [[prometheus]]: switching to
  `portNumber: 15090` makes the symptom vanish, because 15090 *is* declared. Targets come up,
  `istio_requests_total` flows, [[kiali]] looks healthy — and the application's own metrics never
  arrive, because 15090 is Envoy-only. The wrong answer that turns the page green is worse than the
  one that leaves it blank.

  **Not fixed, and reported rather than guessed at:** on that cluster `POST http://shop.localtest.me/orders`
  returns **502**, so no application traffic is flowing and both `orders_received_total` and
  `istio_requests_total` are legitimately empty regardless of the monitor. The app's own
  `:8000/metrics` serves no `orders_received_total` either, which is consistent — the counter does not
  exist until the first order is received. That 502 is at the reader's current point in §9 and is a
  separate thread.

- **2026-08-23** — **The corrected PodMonitor produced nothing, because Argo CD had not applied it.**
  After pushing the chart fix, the §9.6 target check returned zero lines. The instinct — and the one
  the tutorial's wording encouraged — is to go back and debug the monitor.

  It was applied to nothing. `Application/order-platform` reported `sync.status: Synced`,
  `health: Healthy`, `reconciledAt` **72 seconds old** — against `df0a7fc`, while `origin/main` was
  `1251eaf`. Argo polls, and until it does it is *truthfully* synced, to the previous commit. Nothing
  in the object says stale. `kubectl -n argocd annotate app order-platform
  argocd.argoproj.io/refresh=hard --overwrite` moved it to the pushed revision, the live PodMonitor
  picked up the `relabelings`, and Prometheus had **targets `up` on
  `<pod-ip>:15020/stats/prometheus`** within a scrape interval.

  Already recorded on [[argo-cd]] as the `Synced`+`Degraded` stale-cache case (Appendix B). What was
  missing is that **it also presents with nothing wrong at all** — Synced, Healthy, freshly
  reconciled, and simply one commit behind. That variant costs more, because there is no anomaly to
  notice.

  §9.6 now checks the right thing: `Synced` alone is not the check, comparing
  `.status.sync.revision` to `git rev-parse HEAD` is, with the hard-refresh escape hatch and an
  explicit "do not go debug the thing you just changed" — the failure mode here is spending the next
  twenty minutes on an object that was never applied.

- **2026-08-23** — **`istioctl analyze -n shop` exits non-zero on a correct cluster, and the tutorial
  never said so.** Five findings — two `IST0101` on VirtualServices for `frontend` and `pricing`, two
  `IST0127` on AuthorizationPolicies matching no workloads, one `IST0174` on the `pricing`
  DestinationRule — plus `Error: Analyzers found issues`.

  All five are correct and expected. Verified: `shop` holds `order-api` and `order-worker` only;
  `frontend` and `pricing` are built in §17–§19. §9.5's `deny-all` and §9.9's canary routing are
  deliberately written before those workloads exist, because a default-deny policy has to be complete
  before enrolment rather than retrofitted after. Nothing was reported against the two services that
  do exist, which is the part that carries signal.

  **The defect is not the output, it is the silence about it.** §9.5 argues that `istioctl analyze` is
  what catches a `principals` typo naming a nonexistent ServiceAccount — the failure that denies
  everything while `kubectl get pods` looks healthy — and Appendix B sends the reader to the same
  command for `RBAC: access denied`. Pointing someone at a diagnostic without telling them it returns
  five errors when nothing is wrong teaches them to skip its output, and their finding then arrives
  inside a list they have already written off. Same failure as any linter with an unmanaged baseline.

  §9.8 now prints the expected output verbatim, says what clears it and when, points out that the two
  existing workloads are absent from it, and states the rule: **count the findings; six is yours.**
  Extended to [[kiali]]'s Istio Config tab, which validates the same objects and shows the same five
  in red. Appendix B's `RBAC: access denied` row now names the baseline before recommending the
  command. Recorded on [[istio]].

- **2026-08-23** — **The 502 was a Phase 1 Ingress that Phase 4 never told you to remove — and §9.6's
  both-halves check now passes for the first time.**

  Every request to `shop.localtest.me` returned `502 Bad Gateway` while everything else looked right:
  pods `2/2`, Gateway and VirtualService applied, gateway healthy, `istioctl analyze` at its expected
  baseline. `kubectl -n shop get ingress` had the answer — the chart's exact-host Ingress from §10.1
  was still there, recreated by Argo CD from `orderApi.ingress.enabled: true`.

  Exact host beats wildcard, so nginx routed to the `order-api` Service directly, **in plaintext from
  outside the mesh**, and STRICT mTLS refused it. The mesh was healthy; the request never entered it.

  **§9.4 did say to remove them, and got it wrong twice:**

  1. Its only *command* was `kubectl -n shop delete ingress order-api frontend`. Argo CD owns the
     chart — the Ingress comes back on the next reconcile. Same defect as the §9.6 `helm upgrade`
     instruction, in a costume that raises no error: it works, then stops working, with no edit
     nearby to blame. The chart edit was prose above the fence, which is exactly the placement lesson
     from the Kiali move.
  2. It claimed *"two Ingresses claiming the same host and path is a conflict the nginx admission
     webhook rejects outright."* **False.** The hosts differ — `shop.localtest.me` versus
     `*.localtest.me` — so nginx admitted both without complaint and the exact one silently won. The
     doc predicted a loud rejection and the reality is a quiet 502, which is the opposite failure
     mode and sends you looking for a mesh fault that does not exist.

  Fixed: §9.4 now removes the blocks in git, commits, pushes, hard-refreshes and verifies with
  `kubectl -n shop get ingress` → no resources; the warning states the real mechanism and that
  everything you would normally check reports health. Appendix B gained the symptom row.

  **Then §9.6's closing assertion passed, observed, for the first time in this repo's history:**
  `GET /healthz` → 200, `POST /orders` → 202, `orders_received_total` = **41** across 2 series,
  `istio_requests_total` present — including
  `connection_security_policy="mutual_tls"` with
  `source_principal="spiffe://cluster.local/ns/istio-system/sa/istio-ingressgateway"`, which is
  §9.8's evidence sentence, verified rather than reasoned. Removed from [[open-questions]].

- **2026-08-23** — **§9.10 listed 11 lines of a 71-line manifest and then told the reader to apply
  it.** `pricing-fault-injection.yaml.disabled` was shown as *"(abridged — the route block is
  identical to `pricing-traffic.yaml`'s)"*, with `# ... the same 90/10 destinations, timeout and
  retries` standing in for the routing, and no version of the file's 40 lines of operator notes. Four
  lines later: `kubectl apply -f deploy/platform/istio/pricing-fault-injection.yaml.disabled`. Paste
  what is on the page and you have an invalid manifest for a file you were never given.

  Now shown in full, all 71 lines.

  **The same defect as §3.2's `main_test.go` and it recurred, so this time it is a check, not a
  lesson.** `verify_doc_listings.py` gained `elided_but_applied`: a listing that contains an elision
  marker, for a path the docs anywhere tell the reader to `-f`, is a **hard failure**. Two forms are
  caught — a bare `...` line, and a comment whose content *starts* with `...`, which is what an
  abridgement usually dresses itself as. A comment that merely contains an ellipsis in prose is not,
  which was the first cut and produced two false positives on
  `authorization-policy.yaml` and `backstage-secrets.yaml`.

  Verified by reintroducing the original elision and confirming the checker exits 1 naming that line,
  then restoring. `failures: 0` on the current tree.

  **The rule it encodes:** *a listing the reader is told to apply must be paste-able.* Elide comments
  if the page needs to breathe; never elide structure. [[progressive-build]] already said a
  subsequence test proves a listing is not stale and proves nothing about whether it is sufficient —
  that observation is now enforced for the one case where insufficiency is guaranteed to bite.

- **2026-08-23** — **Snippets are banned; every listing is now a whole file.** After §9.10's abridged
  manifest, the human set the rule: *"there should never be a case ever again where I can't copy the
  code and have it work."* Audited all 41 tracked listings in `docs/` and fixed **20**.

  Method, because "looks complete" is not a test: parse every listing standalone for its file type
  (YAML via Ruby's parser, `compile()` for Python, `bash -n` for shell, package/syntax clauses for Go
  and proto) — **all 41 passed**, which is the point. The breakage was never syntactic. A single
  Python function with no imports compiles fine and is still not a file. So the real classifier was
  comparing each listing's non-comment lines against the repo file: `IDENTICAL`, `COMMENTS-ONLY`,
  `PARTIAL n/m`, `DIVERGED`.

  What that found, and what was done:

  - **6 `(comments stripped)` listings** — `edge-gateway.yaml`, `edge-ingress.yaml`, `pricing.proto`,
    two `BUILD` files, `settings.py`. Mechanically replaced with the full files.
  - **4 fragments of single-stage files** — `authorization-policy.yaml` (61/81 lines),
    `pricing-traffic.yaml` (26/54), `scaffolded.yaml`, `services/pricing/BUILD`. Confirmed each
    listing was a subsequence of the file before substituting, so nothing was invented.
  - **6 listings differing only in whitespace or comments** — the Argo CD apps, `catalog-info.yaml`,
    `app-config.production.yaml`, `order-worker.yaml`. Replaced.
  - **4 genuine "edit an existing file" snippets** — `.yarnrc.yml`, `index.ts` ("add one line next to
    the other `backend.add(...)` calls"), `services/pricing/pricing/main.py` shown as **one function
    with no imports**, and phase-7's `test_api.py` starting at `class _FakePricingClient:`. All now
    whole files.

  **The one that could not be substituted:** §14's `.buildkite/pipeline.sh`, a 40-line block you were
  told to splice in "after the services loop, before the deploy step". Pasting the end-state file
  there would leak §19.5's Pants steps into a phase that has not built them. Reconstructed from
  §12.5's whole-file listing plus the portal block, then verified — `bash -n` clean, executed against
  the repo, output parsed as YAML, six step labels read back including `:backstage: build portal`. 314
  lines, and it runs.

  **What is left, and why it is correct:** 12 listings still differ from the end-state file. Every one
  starts at the top of its file and is a complete, pasteable snapshot of an earlier *stage* —
  `main.py` at 107 of its eventual 231 lines before gRPC exists, the two Dockerfiles before Pants
  shrinks them, `values.yaml` before three more services. That is the progressive build working as
  designed, and flattening it would hand the reader code importing services they have not built.

  `verify_doc_listings.py` now hard-fails on any elision marker under a bolded path — a bare `...`
  line or a comment whose content *starts* with `...`. Prose containing an ellipsis does not match;
  that was the first cut and it false-positived on `authorization-policy.yaml` and
  `backstage-secrets.yaml`. Verified by reintroducing an elision into `pipeline.sh`: exits 1, names
  the line. Recorded on [[progressive-build]].

- **2026-08-23** — **§14.2's `curl` cannot fail visibly, so its failure arrives as a Yarn 404 two
  sections later.** Reported: `yarn add @backstage/plugin-scaffolder-backend-module-github` →
  `YN0035: Package not found / Response Code: 404 (Repository not found)`.

  Checked the registry rather than the package name:
  `curl -s http://localhost:8081/service/rest/v1/repositories` returned ten repositories and
  **`npm-proxy` was not among them**. The package name was never the problem — *"Repository not
  found"* is Nexus talking about **itself**.

  Why nobody noticed at §14.2: `POST /service/rest/v1/repositories/npm/proxy` returns `201` with an
  **empty body** on success and `401`/`400` with an **equally empty body** on failure, and the
  tutorial's command carried no `-f`, no `-w '%{http_code}'`, no check. A rejected create prints
  exactly what a successful one prints: nothing. The verification line that followed dumped all
  repository names and asked the reader to eyeball a ten-item list for one entry.

  Fixed: `-f` plus `%{http_code}` on the create, and the check is now an assertion —
  `jq -e '.[] | select(.name == "npm-proxy")'` — not a list to read. The warning states that "Repository
  not found" is about the repository, since every instinct on seeing it is to go check the package
  name and the Yarn config, both of which are correct.

  **And the credential is wrong in the docs, again.** Attempting the create with the documented
  `admin:admin123` returned **401** — this Nexus's admin password is not what the tutorial suggested,
  `/nexus-data/admin.password` is deleted on first login so it cannot be recovered, and three wrong
  attempts trip the 900s lockout ([[sonatype-nexus]]). Stopped at one attempt. §14.2 now takes
  `$NEXUS_ADMIN_PASSWORD` and says outright that it is whatever was set at §5.2, not necessarily
  `admin123`. Same shape as the `ci` password: **the tutorial printed a value and the platform kept a
  different one**, and every place the docs hardcode a credential is a place that drifts.

  Appendix B gained the symptom row.

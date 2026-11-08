# Open questions

Things we don't know, with what it would take to settle them. `/wiki-ask` should remove entries it
answers and add ones it hits. An empty list here means we stopped being curious, not that we're done.

Rebuilt 2026-08-17 alongside the rest of the wiki. Entries are derived from the current state of
`docs/` and the repo, not carried forward.

## What has never been observed

The platform was built on a live [[kind]] cluster through §13. Everything below is **documented, not
observed**, and every entry here would be settled by one successful run.

- **§14–§16 have never run.** [[kiali]], [[backstage]] and the [[prometheus]]/[[grafana]] stack are
  written from their manifests and their vendor docs. Their pages carry
  `status: documented-not-observed`.
- **The canary and the fault-injection drill have never been run against a live cluster.** §9.9 and
  §9.10 are written from the manifests and their reasoning, and every manifest passes
  `kubectl apply --dry-run=server` against the live CRDs — but the 90/10 split, the weight shift, the
  retry envelope and the outlier ejections are documented, not observed. **The claim that a
  client-side injected delay counts toward `consecutive5xxErrors` at order-api's sidecar is reasoned
  from Envoy's behaviour and is the least verified sentence in the phase.** *To settle:* run the drill
  and record what the frontend and Kiali actually showed. See [[timeouts-and-retries]].
- **Has a service ever been scaffolded end to end?** The `new-service` skeleton now emits a `BUILD`
  file, which is what makes CI discover it (§19.5). Whether §15.5's walkthrough completes — form → PR →
  merge → build → deploy → `curl http://quotes-api.localtest.me/healthz` — is untested. *To settle:*
  run it once. See [[paved-paths]].
- **Does the PEX first-run extraction cost enough startup latency to matter?** An `emptyDir` starts
  empty, so every fresh pod pays the unpack. For `grpcio` + `pydantic-core` that is plausibly seconds,
  and it lands inside the readiness probe budget. Nobody has measured it. *To settle:* time `pricing`'s
  container from start to first successful `/readyz`, and compare against a `--venv` mode PEX. See
  [[pex]].

## Version drift found while rebuilding this wiki

Recorded rather than fixed, per rule 7 — the docs are the source and a wiki operation does not edit
them.

- **Backstage `create-app`:** Appendix A says **1.53.1**; `portal/backstage.json` says **1.53.0**.
  *To settle:* decide which is authoritative and align the other. Low stakes, but Appendix A claims
  every version was read back from a running workload.
- **Helm:** Appendix A and §1.2 give a floor of **≥3.8.0** (OCI support). `.buildkite/pants-ci.Dockerfile`
  pins **4.2.4**, a major version the docs never mention. *To settle:* confirm the chart still lints
  and templates identically under Helm 3 and 4, and state the CI version in Appendix A.
- **Go:** Appendix A says **1.26.x**; `go.mod` requires **1.26.5** and the CI image copies from
  **golang:1.26.6** with `GOTOOLCHAIN=local`. Not a contradiction, but the patch-pinning discipline is
  load-bearing and Appendix A does not mention it. See [[go]].

## Istio

- **Is native sidecar support on by default in Istio 1.30?** Sidecars *are* injected as native sidecars
  on Kubernetes 1.29+ in this cluster (they appear as `initContainers` with `restartPolicy: Always`).
  If that is on by default, Jobs in enrolled namespaces stop hanging and the `buildkite` namespace
  could join the mesh — which §9.3 currently excludes for exactly that reason. *To settle:* Istio docs
  on native sidecars, plus `istiod` env for `ENABLE_NATIVE_SIDECARS`.
- **What does enrolling `monitoring` actually cost**, versus the merged-metrics approach we took?
  *To settle:* deploy both ways, compare pod memory and the node-exporter opt-out burden.
- **Does traffic from `kubectl port-forward` really hit the inbound mTLS listener?** §6.4 asserts it
  does. Verified by reasoning about iptables capture, not by running it. *To settle:* run it against a
  STRICT namespace.

## Kubernetes / kind

- **Which Kubernetes version does kind v0.32.0 pin**, and is it inside Istio 1.30's support window
  (~1.32–1.36)? Appendix A gives the window but not the pinned version. *To settle:*
  `kind create cluster` then `kubectl version`.

## Networking

- **Would swapping `kindnetd` for Calico or Cilium break anything else here?** [[cni]] establishes that
  NetworkPolicy is inert on this cluster and that changing the CNI is the prerequisite for closing
  Appendix C's gap. What that costs is unmeasured: kind documents `disableDefaultCNI` as an advanced
  feature with limited support, and the interaction with [[istio]]'s iptables redirection and with
  `hostPort` on the control-plane node ([[ingress-nginx]]) is untested here. *To settle:* stand up a
  second cluster with `disableDefaultCNI: true` plus Calico and run §15's end-to-end checks.

## Nexus

- **Minimum privilege set for a push-only CI user.** §5.5 uses `nx-admin` and Appendix C calls this the
  quickest real improvement available. *To settle:* Nexus privilege reference plus trial and error.
- **Does trimming `nx-anonymous` to the two proxy view privileges actually hold?** The reasoning is from
  Sonatype's docs and the per-repository Docker switch, and enabling global anonymous access was
  verified to fix CI — but the **narrowed** role has not been applied and re-tested. *To settle:* trim
  the role to `nx-repository-view-pypi-pypi-proxy-*` and `nx-repository-view-go-go-proxy-*`, re-run a
  build, and confirm `docker pull` still demands credentials. See [[sonatype-nexus]].
- **The npm proxy is created by `curl` against the REST API (§14.2), not through the UI like the other
  three.** Nothing records why. *To settle:* trivial, but worth stating — either make all four
  consistent or say why npm is different.

## Floci

- **Which AWS behaviours does Floci not emulate faithfully?** IAM policy evaluation, DynamoDB throttling
  and S3 consistency are the usual suspects. *To settle:* Floci docs plus targeted probes.
- **Is there any free way to exercise IAM policy evaluation locally?** This is the one place
  [[enterprise-substitution]] leaves a real *teaching* gap rather than a licensing one: Floci accepts
  credentials and never authorises them, so a reader finishes this tutorial having **never tested an
  IAM policy**. LocalStack charges for IAM enforcement. *To settle:* check whether Floci enforces IAM
  at all today, and whether `simulate-principal-policy`-style tooling covers it offline.

## Backstage

- **Can a discovery provider auto-register new `catalog-info.yaml` files within a single repo?** This is
  the one seam the infra paved path leaves for a human (§14.7). *To settle:*
  `@backstage/plugin-catalog-backend-module-github` docs on `catalogPath` wildcards.
- **Is a GitHub App feasible with no inbound webhook URL on a laptop?** Needed to attribute scaffolder
  PRs to real users instead of one shared token.
- **Which Postgres operator** should replace the bundled `bitnamilegacy` subchart? See [[postgresql]].

## The build system

- **Five of the eight Pants backends we depend on are `experimental.*`** — ruff check, ruff format, go,
  protobuf-go, javascript, typescript. The stated mitigation is that each has a one-command escape
  hatch. *To settle:* nothing to settle by research — this is a bet whose cost only appears at a Pants
  upgrade. Worth re-reading the release notes before bumping `pants_version`, and worth recording here
  if a backend breaks or graduates. See [[pants]].
- **Is the `[python-bootstrap] search_path` Homebrew entry portable?**
  `/opt/homebrew/opt/python@3.13/libexec/bin` is Apple-silicon-specific; an Intel Mac uses
  `/usr/local/opt/...` and a Linux workstation neither. *To settle:* confirm whether `<PATH>` alone
  suffices on Linux, and whether the entry should be a documented per-machine override rather than a
  committed default.

## Platform-wide

- **The Buildah build-and-push steps have never completed.** The `nexus-push` credential is verified
  working (HTTP 200 against `/v2/_catalog`), but `buildah bud` under `vfs` with the named capability
  set, and the push to `nexus:8082`, are unexercised end to end. *To settle:* one green build. See
  [[buildah]].
- **What deleted the Argo CD `root` Application on 2026-08-15?** The cascade delete that tore down the
  platform was traced precisely, but the originating command was not. No audit log was available.
  *To settle:* enable Argo CD audit logging, or shell history discipline. See [[argo-cd]].
- **Nothing measures whether the paved path is actually the easiest path.** [[paved-paths]] rests
  entirely on that claim and this platform has one user. *To settle:* not researchable — it needs a
  second person and a stopwatch.

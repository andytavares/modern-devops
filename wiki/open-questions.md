# Open questions

Things we don't know, with what it would take to settle them. `/wiki-ask` should remove entries it
answers and add ones it hits. An empty list here means we stopped being curious, not that we're done.

## Istio

- **Is native sidecar support (Kubernetes ≥1.29) on by default in Istio 1.30?** If yes, Jobs in
  enrolled namespaces stop hanging and the `buildkite` namespace could join the mesh.
  *To settle:* Istio docs on native sidecars + check `istiod` env for `ENABLE_NATIVE_SIDECARS`.
- **What does enrolling `monitoring` actually cost**, versus the merged-metrics approach we took?
  *To settle:* deploy both ways, compare pod memory and the node-exporter opt-out burden.
- **Does traffic from `kubectl port-forward` really hit the inbound mTLS listener?** The tutorial
  asserts it does. Verified by reasoning about iptables capture, not by running it.
  *To settle:* run it against a STRICT namespace.

## Kubernetes / kind

- **Which Kubernetes version does kind v0.32.0 pin**, and is it inside Istio 1.30's support window
  (~1.32–1.36)? *To settle:* `kind create cluster` then `kubectl version`.

## Nexus

- **Minimum privilege set for a push-only CI user.** The tutorial uses `nx-admin` and calls this out
  as the quickest real improvement available. *To settle:* Nexus privilege reference + trial and error.

## Floci

- **Which AWS behaviours does Floci not emulate faithfully?** IAM policy evaluation, DynamoDB
  throttling and S3 consistency are the usual suspects. *To settle:* Floci docs + targeted probes.

## Backstage

- **Can a discovery provider auto-register new `catalog-info.yaml` files within a single repo?** This
  is the one seam the infra paved path leaves for a human (§14.7).
  *To settle:* `@backstage/plugin-catalog-backend-module-github` docs on `catalogPath` wildcards.
- **Is a GitHub App feasible with no inbound webhook URL on a laptop?** Needed to attribute scaffolder
  PRs to real users instead of one shared token.
- **Which Postgres operator** should replace the bundled `bitnamilegacy` subchart?

## Platform-wide

- ~~**Does the chart's `PodMonitor` actually reach the merged metrics endpoint?**~~ **Settled
  2026-08-16: no, it did not.** It selected `port: http-envoy-prom` = **15090 = Envoy-only**. Istio's
  docs are explicit — *"forwards requests to the sidecar telemetry port 15020 for merged metrics or
  15090 for Envoy-only metrics"* — and a live sidecar confirms it: 15090 serves `envoy_*` +
  `istio_requests_total`, 15020 serves those plus `istio_agent_*` and the merged application metrics.
  So Kiali would have worked while `orders_received_total` never appeared, and §13.3's first check
  could not pass. Fixed to `portNumber: 15020` (15020 is **unnamed** in the pod spec, so `port:`
  cannot address it; `targetPort` is deprecated in favour of `portNumber`). See [[prometheus]],
  [[istio]].

- ~~**Nothing in this wiki has been executed end to end.**~~ **Superseded 2026-08-16.** The platform
  has been built on a live kind cluster through §13: Nexus, Floci, OpenBao + ESO, Kafka/Strimzi, Istio
  with STRICT mTLS, Argo CD app-of-apps and Buildkite CI all ran. **Still unobserved:** Kiali,
  Backstage and the Prometheus/Grafana stack (§14–§16) — those manifests remain *documented*, not
  *observed*.
- **The Buildah build-and-push steps have never completed.** CI reached them only after the test steps
  were fixed on 2026-08-16. The `nexus-push` credential itself is verified working (HTTP 200 against
  `/v2/_catalog`), but `buildah bud` under `vfs` in a privileged pod, and the push to `nexus:8082`,
  are unexercised. *To settle:* one green build.
- **Does trimming `nx-anonymous` to the two proxy view privileges actually hold?** The reasoning is
  from Sonatype's docs and the per-repository Docker switch, and enabling global anonymous access was
  verified to fix CI — but the *narrowed* role has not been applied and re-tested. *To settle:* trim
  the role, then re-run a build and confirm `docker pull` still demands credentials. See
  [[sonatype-nexus]].
- **What deleted the Argo CD `root` Application on 2026-08-15?** The cascade delete that tore down the
  platform was traced precisely (see [[argo-cd]], [[strimzi]]), but the originating command was not.
  No audit log was available. *To settle:* enable Argo CD audit logging, or shell history discipline.

## The monorepo build system (added 2026-08-16)

- **The paved path now produces services the pipeline cannot build.** The [[backstage]] skeleton
  emits `pyproject.toml` and `uv.lock` and **no `BUILD` file**, so a scaffolded service arrives
  outside the [[pants]] monorepo — and CI now discovers services by the presence of `services/*/BUILD`
  (§19.5). A service created through the form is therefore not linted, tested, packaged or built.
  This is a regression in [[paved-paths]] introduced by the migration, and it is known: `ae9a448`
  fixed the package-name half of the problem and explicitly deferred this half. *To settle:* make the
  skeleton emit a `BUILD` file with `python_sources` / `python_tests` / `pex_binary`, drop the
  per-service `pyproject.toml` and `uv.lock`, and scaffold one service end to end.
- **Five of the eight Pants backends we depend on are `experimental.*`.** go, protobuf-go, javascript,
  typescript and ruff. The stated mitigation is that each has a one-command escape hatch. *To settle:*
  nothing to settle by research — this is a bet whose cost only appears at a Pants upgrade. Worth
  re-reading the release notes before bumping `pants_version`, and worth recording here if a backend
  breaks or graduates.
- **The canary and the fault-injection drill have never been run against a live cluster.** §9.8 and
  §9.9 are written from the manifests and their reasoning, and every manifest passes
  `kubectl apply --dry-run=server` against the live CRDs — but the 90/10 split, the weight shift, the
  retry envelope and the outlier ejections are *documented*, not *observed*. The claim that a
  client-side injected delay counts toward `consecutive5xxErrors` at order-api's sidecar is reasoned
  from Envoy's behaviour and is the least verified sentence in the phase. *To settle:* run the drill
  and record what the frontend and [[kiali]] actually showed.
- **Does the PEX first-run extraction cost enough startup latency to matter?** An `emptyDir` starts
  empty, so every fresh pod pays the unpack. For `grpcio` + `pydantic-core` that is plausibly seconds,
  and it lands inside the readiness probe budget. Nobody has measured it. *To settle:* time
  `pricing`'s container from start to first successful `/readyz`, and compare against a `--venv` mode
  PEX. See [[pex]].
- **§17–§19 exist only in the phased edition.** `modern-devops-tutorial.md` has no Pants, proto,
  pricing, PEX or frontend material, so the two editions no longer carry the same section set — which
  contradicts `docs/README.md`'s promise that `§N.M` means the same thing in both. Every *existing*
  number still does. *To settle:* port §17–§19 into the single-document edition, which is a tutorial
  change and therefore the human's call.

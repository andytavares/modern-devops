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

- **Nothing in this wiki has been executed end to end.** The Buildkite pipeline generator and the Helm
  chart templates were run and verified; the Istio, Kiali and Backstage manifests were assembled from
  current vendor docs but never applied to a live cluster. Treat runtime claims about those three as
  *documented*, not *observed*, until someone builds the cluster.

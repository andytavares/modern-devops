---
type: tool
tags: [packaging, delivery]
role: packaging — ours, and everyone else's
version: ≥ 3.8.0 required (OCI); the CI image ships 4.2.4
docs: https://helm.sh/docs/
date_added: 2026-08-17
date_updated: 2026-08-17
status: in-use
---

# Helm

> [!info] One-liner
> Go templates producing YAML. It is how nine of the components here are installed, and how our own workloads are packaged into [[order-platform]].

## Two distinct jobs it does here

**Installing other people's software.** [[openbao]], [[external-secrets-operator]], [[strimzi]],
[[istio]] (three charts), [[prometheus]] (kube-prometheus-stack), [[kiali]], [[buildkite]]
(agent-stack-k8s, from OCI), [[backstage]]. Values files live in `infra/`. This is the job Helm is
unambiguously right for.

**Packaging ours.** `deploy/charts/order-platform` — see [[order-platform]] for the chart itself.

## Helm vs Kustomize, and why this repo is on the "wrong" side (§10.6)

| | Helm | Kustomize |
|---|---|---|
| Mechanism | Go templates → YAML | Strategic merge patches on real YAML |
| Best at | distributing to strangers; conditional output | overlaying environments onto manifests you own |
| Failure mode | template logic becomes a program nobody can read | patch files multiply; final object needs rendering to see |
| Versioned artifact | yes | no native packaging |
| Rollback | `helm rollback` (in-cluster history) | whatever git says |

The rule of thumb: **Helm for software you ship to others, Kustomize for software you run yourself.**
This platform is technically on the wrong side and does it anyway, because you will spend your career
reading other people's charts. [[argo-cd]] supports both natively, so this is not a lock-in decision.

## Idioms this repo leans on

**`helm template` before you trust it, every time (§10.3).** And a step further —
`helm template … | kubectl apply --dry-run=server -f -` catches schema errors against the live API
without applying. CI does both, plus `helm lint --strict`, in the verify step (§19.5).

**`checksum/config` annotations to force a roll.** Without one, `helm upgrade` with only a value change
leaves old pods running. `pricing.yaml` uses Helm's documented form —
`{{ include (print $.Template.BasePath "/configmap-pricing.yaml") $ | sha256sum }}` — naming *that
service's* ConfigMap. Hashing `.Values` instead restarts every pod in the namespace on every deploy,
because CI rewrites image tags in the env overlay on every build (§19.3).

**`.Files.Glob` to make onboarding a file creation.** `scaffolded.yaml` ranges over
`services/*.yaml` rather than reading `values.yaml`, so adding a service is conflict-free and
trivially reviewable rather than an edit to a shared file (§14.6). **When designing a paved path, bias
every step towards adding a file rather than editing one.** See [[paved-paths]].

> [!warning] A file that is not valid YAML renders as **nothing**, with no error
> A scaffolded service whose chart file is malformed simply does not appear. `helm template … | grep`
> is how you find it (Appendix B).

> [!warning] A `BUILD` file inside `templates/` is rendered as a manifest
> [[pants]] wants `BUILD` files everywhere; Helm renders everything in `templates/`. One inside that
> directory broke `helm template` outright. `pants_ignore` and target placement have to respect the
> chart's directory contract.

## Related

[[order-platform]] · [[argo-cd]] · [[kubernetes]] · [[paved-paths]] · [[pants]]

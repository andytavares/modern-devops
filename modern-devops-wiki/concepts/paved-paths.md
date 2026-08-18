---
type: concept
tags: [platform-engineering, developer-experience]
date_added: 2026-08-17
date_updated: 2026-08-17
---

# Paved paths

> [!info] One-liner
> A document made executable. The measure is not that it makes the first service easy — it is that it makes the fiftieth service identical to the first.

## The rule that makes it work

> **The paved path must be the easiest path.** If the golden path is a form producing a reviewed PR in
> ninety seconds, and the alternative is copying another service's directory and guessing, people take
> the form. **If the paved path is slower than copy-paste, you have built a portal nobody uses and a
> wiki page with better formatting.**

The usual alternative — a wiki page titled *How to add a service* — decays within two sprints, because
**nothing breaks when it goes stale.**

## What makes these two paths actually work

Neither template edits a pipeline and neither touches the cluster. They work because of decisions made
three phases earlier:

| Decision | Made in | What it buys |
|---|---|---|
| [[buildkite]] discovers services from the filesystem (`BUILD` + `Dockerfile`) | §12.5, §19.5 | A new service needs no CI edit |
| [[pants]] selects the package set by `--tag=deployable` | §19.5 | CI packages a service **without CI knowing it exists** |
| The chart globs `services/*.yaml` via `.Files.Glob` | §14.6 | Onboarding is a file *creation*, not an edit |
| [[argo-cd]] recurses `deploy/platform` | §11.4 | An infra manifest deploys itself |
| The [[istio]] Gateway takes a **wildcard** host | §9.4 | A new route needs no edge object |
| The namespace is enrolled in the mesh in git | §9.3 | A new pod gets a sidecar automatically |

## Bias every step towards adding a file rather than editing one

`.Files.Glob` over `values.yaml` is the clearest instance. A chart normally takes input from
`values.yaml`, which makes onboarding an **edit to a shared file** — merge conflicts when two teams
onboard the same week, and a diff reviewers must read carefully. Reading a directory instead makes it
conflict-free, trivially reviewable and trivially revertible.

## Narrow on purpose

No per-service Kafka topic, no per-service secret, no autoscaling. **A paved path earns trust by being
narrow and predictable; the moment it grows a checkbox for everything, it becomes a worse version of
writing the YAML by hand.** Services needing more should fall off the path deliberately and copy the
chart's explicit `order-api.yaml`.

## Details in the templates that are load-bearing

- **PRs, never direct pushes.** *A paved path that bypasses review is not a path, it is a hole.*
- **The package directory is `${{ values.name | replace('-', '_') }}`, not `app`.** Every service under
  the shared `/services/*` source root that ships an `app` package collides with every other one. See
  [[pants]].
- **The metric prefix is computed in Python, not templated.** `SERVICE.replace("-", "_")`, because
  service names are hyphenated and Prometheus metric names may not be. Doing it in code means a rename
  can never produce an invalid metric name, and a test asserts exactly that.
- **The skeleton carries a `/tmp` emptyDir and `PEX_ROOT`.** Without them every scaffolded service
  crash-loops in the [[pex]] bootstrap before any log line appears.
- **The scaffolded template got the same mesh-edge fix as the hand-written services.** Otherwise every
  service produced by a paved path ships broken — *which is the worst possible first impression of a
  golden path.*

## Count what still needs a human (§15.5)

The PR needs a reviewer. The new service has no Kafka topic, no secret, no dashboard of its own. And
its `catalog-info.yaml` only reaches [[backstage]] once the root catalog file references it — Backstage
discovers catalog files from *configured locations*, and a brand-new file in an existing repo is not
one until someone adds a location entry or enables the GitHub discovery provider. **That is the one
place this paved path still needs a human to do a second thing**, and it is stated rather than
pretended away.

> **A paved path is a floor, not a ceiling.** The moment you pretend it is a ceiling, teams route
> around it and you are back to copy-paste with extra steps.

## Related

[[backstage]] · [[dynamic-pipelines]] · [[order-platform]] · [[pants]] · [[helm]] · [[argo-cd]] · [[istio]] · [[pex]]

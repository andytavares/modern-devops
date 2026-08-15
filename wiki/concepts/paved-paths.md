---
type: concept
tags: [platform-engineering, developer-experience]
docs: https://backstage.io/docs/features/software-templates/
date_added: 2026-08-15
date_updated: 2026-08-15
---

# Paved paths (golden paths)

> [!info] One-liner
> The documented way to do something, made executable — and it only works if it is genuinely the *easiest* way.

## The rule

> **The paved path must be the easiest path.** If the golden path is a form that produces a reviewed PR
> in ninety seconds and the alternative is copying another service's directory and guessing, people
> take the form. If the paved path is slower than copy-paste, you have built a portal nobody uses and
> a wiki page with better formatting.

A wiki page titled *How to add a service* decays within two sprints, because nothing breaks when it
goes stale. A template breaks loudly.

## Design principles that made ours work

1. **Produce a pull request, never a direct push.** A paved path that bypasses review is a hole.
2. **Bias every step towards adding a file rather than editing one.** Creation is conflict-free and
   trivially reviewable; editing a shared values file causes merge conflicts and careful-reading
   diffs. This is why the chart uses `.Files.Glob` and CI globs `services/*/Dockerfile` (§14.6).
3. **The path should require no changes to CI or CD.** If onboarding a service means editing the
   pipeline, the pipeline is the bottleneck and the path isn't paved.
4. **Keep it narrow.** No per-service Kafka topic, no autoscaling checkbox. The moment it grows an
   option for everything, it becomes a worse version of writing the YAML by hand.
5. **Falling off the path must be legal.** Services with unusual needs copy the explicit chart
   templates instead. A path is a floor, not a ceiling — pretend otherwise and teams route around it.

## What it costs

Someone owns the templates. They rot exactly like documentation, just more visibly. And the platform
itself is usually the least-paved thing in the cluster — in this project [[backstage]] is deployed by
a hand-run `helm install` while everything it onboards goes through GitOps (§14.8). That irony is
normal; notice it, then fix it.

## How it's implemented here

[[backstage]] scaffolder templates in `deploy/backstage/templates/`, using `fetch:template` +
`publish:github:pull-request`. Two paths: new service, new S3 bucket. The bucket one emits a
one-shot Job — the production answer is a reconciled resource (Crossplane / ACK), and the tutorial
says so plainly (§14.7).

> [!tip] Related
> [[backstage]], [[gitops]], [[argo-cd]], [[helm]], [[dynamic-pipelines]]

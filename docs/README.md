# Build a DevOps platform, one working thing at a time

A production-shaped platform on your laptop: two services, a registry, secrets, events, GitOps, CI, a
service mesh, and a developer portal. No cloud account, no credit card.

This is the phased edition. Every phase ends with something that **works and that you can check**, and
each one exists because the previous one left a specific problem unsolved. If you stop after any
phase, you are left with a coherent system rather than a half-built one.

> The single-document edition is [`../modern-devops-tutorial.md`](../modern-devops-tutorial.md). Same
> content, same section numbers — this edition regroups it into the order you'd actually build it.
> Section references like `§7.6` mean the same thing in both.

## The phases

| | Phase | You end with | Sections |
|---|---|---|---|
| **0** | [Foundations](phase-0-foundations.md) | A cluster with an edge, and a registry all three resolvers agree on | §1, §2, §4, §5 |
| **1** | [The application, running](phase-1-the-application.md) | `POST /orders` → `202` → a row in DynamoDB | §3, §6, §7, §8, §10 |
| **2** | [Seeing what it does](phase-2-observability.md) | A dashboard of real traffic, and one alert worth waking for | §13 |
| **3** | [Delivery](phase-3-delivery.md) | `git push` deploys; the cluster holds no CI credentials | §11, §12 |
| **4** | [Identity between services](phase-4-service-mesh.md) | mTLS everywhere, default-deny, the graph, and a canary | §9 |
| **5** | [Someone else's platform](phase-5-developer-portal.md) | A form that yields a reviewed PR that deploys itself | §14 |
| **7** | [One build system, many languages](phase-7-polyglot-monorepo.md) | One command builds Python, Go and TypeScript; one `.proto` compiles into two of them | §17, §18, §19 |
| **6** | [Operating it](phase-6-operating.md) | A platform you have broken six ways and recovered | §15, §16 |
| | [Appendices](appendices.md) | Versions, troubleshooting, omissions, commands | A–D |

> **Phase 7 is out of numerical order on purpose, and that is not a typo.** The number records when it
> was built — the monorepo arrived after the platform was already running — and the position records
> where it belongs when reading. See [Why this order](#why-this-order). Renumbering it would have
> renumbered its sections, and `§N.M` is a stable reference this wiki and both editions cite.

## Why this order

Each phase is here because the one before it created the problem it solves.

```
0  Foundations      no cluster, no registry
                        ↓  now you can run and pull things
1  The application  works, but you deploy it by hand and can't see it
                        ↓  "is it healthy?" has no answer
2  Observability    now you can see it — and deploying by hand is the bottleneck
                        ↓  fast deploys are only safe if you can watch them
3  Delivery         git is the deploy button — but every pod trusts every pod
                        ↓  "same network" is not identity
4  Service mesh     identity-based trust — and it breaks your monitoring, on purpose
                        ↓  the platform works; only you can use it
5  Developer portal a form, a PR, a deploy
                        ↓  now services are cheap to add, and every one costs a CI step
7  Polyglot monorepo one build system, one proto, two languages checked together
                        ↓  it all works when nothing is wrong
6  Operating it     break it deliberately, then throw it away
```

Four of those transitions are worth stating outright, because they are choices and not everyone
makes them the same way.

**Deploy by hand in Phase 1, hand it to Argo CD in Phase 3.** You could start with GitOps. You would
learn less. `helm install` from a laptop is what most teams actually do first, and the specific
miseries of it — you must be present, you must remember the tag, nothing records what you did — are
the argument for Phase 3. A tool whose absence you have not felt is a tool you will misconfigure.

**Monitoring before the mesh.** The mesh breaks plaintext scraping. Doing observability first means
that break happens *to something you built and understand*, with the fix in front of you
([§9.6](phase-4-service-mesh.md#96-the-metrics-problem-you-just-created)). Doing the mesh first turns
the same lesson into a footnote you skim.

**The portal last.** A paved path over a platform you are still changing paves the wrong route.

**The build system after the portal, and before the teardown.** [Phase 7](phase-7-polyglot-monorepo.md)
is the one that reads out of order, so here is the argument. A monorepo build system is not something
you adopt because it is sophisticated — with one service in one language it is pure overhead and `uv`
is the better answer. You adopt it when you can name what it fixes, and the two things it fixes here
are *made* by the phases before it. Phase 5 makes adding a service cheap, so the per-language CI steps
of [§12.5](phase-3-delivery.md#125-the-pipeline) become a file someone must hand-edit on every use of
the paved path. And a platform with three services has a shared data contract enforced by nothing but
code review. Doing this earlier means installing a large dependency against problems you have not felt
— the same mistake the `helm install`-before-GitOps argument above is about.

It goes *before* Phase 6 because Phase 6 ends by deleting the cluster, and nothing sensibly follows
that. It also gives Phase 6 something to break: `pricing` is the first synchronous call between two
services in this platform, which is what makes
[§9.8](phase-4-service-mesh.md#98-canary-two-versions-of-pricing-behind-one-service)'s canary and
[§9.9](phase-4-service-mesh.md#99-break-it-on-purpose-fault-injection)'s fault-injection drill
runnable at all.

> **Phase 7's sections are new material and exist only in this edition so far.** §17, §18 and §19 have
> no counterpart in [`../modern-devops-tutorial.md`](../modern-devops-tutorial.md) yet. Every other
> section number still means the same thing in both.

## What you need

A laptop with 8 CPU / 16 GB free, Docker, and about a day. Full list and pinned versions:
[§1](phase-0-foundations.md#1-prerequisites) and
[Appendix A](appendices.md#appendix-a--version-matrix).

Everything is pinned and verified against a running cluster, not read off a changelog. When something
fails, [Appendix B](appendices.md#appendix-b--troubleshooting) is organised by the **symptom you see**
rather than the component at fault, because at the point of failure you do not yet know the component.

## How to read it

Type the commands. Every phase has verification steps that are worth doing rather than skimming —
several of them exist specifically because a plausible-looking cluster was silently broken. The
callouts marked with a warning are, without exception, failures that actually happened while building
this and cost real time.

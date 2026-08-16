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
| **4** | [Identity between services](phase-4-service-mesh.md) | mTLS everywhere, default-deny, and the graph | §9 |
| **5** | [Someone else's platform](phase-5-developer-portal.md) | A form that yields a reviewed PR that deploys itself | §14 |
| **6** | [Operating it](phase-6-operating.md) | A platform you have broken six ways and recovered | §15, §16 |
| | [Appendices](appendices.md) | Versions, troubleshooting, omissions, commands | A–D |

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
                        ↓  it all works when nothing is wrong
6  Operating it     break it deliberately, then throw it away
```

Three of those transitions are worth stating outright, because they are choices and not everyone
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

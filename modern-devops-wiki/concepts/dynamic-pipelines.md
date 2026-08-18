---
type: concept
tags: [ci, delivery]
date_added: 2026-08-17
date_updated: 2026-08-17
---

# Dynamic pipelines

> [!info] One-liner
> `buildkite-agent pipeline upload` reads YAML on stdin, so the pipeline can be *generated* at the start of a build by a script that knows things a static file cannot.

## The three wins, in the order they matter here (§12.5)

1. **The loop guard runs before any pod starts.** A deploy commit produces a one-step pipeline instead
   of running the full test-and-build cycle and throwing the result away at the end.
2. **The per-service steps stop being copy-paste.** As hand-maintained YAML twins differing only in a
   name, they drift — and the drift is silent. One template in a `for` loop cannot.
3. **No `$$` escaping anywhere.** The generator substitutes the SHA and registry host *as it writes the
   YAML*, so the emitted pipeline contains no `$` at all, and Buildkite's upload-time interpolation of
   `$VAR` — the classic source of silently-empty variables — has nothing left to bite.

## The price, stated plainly

**A YAML syntax error in a static pipeline is caught before the build starts; in a generated one it
appears mid-build.** `.buildkite/upload.sh` buys most of that back with a `--dry-run`, and keeps the
exact YAML as a build artifact so a surprising build can be read after the fact.

> [!warning] Do not pipe the generator into the uploader
> `pipeline.sh | buildkite-agent pipeline upload` hides failures: a pipe's exit status is the **last**
> command's, so a generator that dies half-way still uploads whatever it managed to print and the step
> goes green. Write to a file under `set -e` instead.

## Discovery, which is what makes the paved path work

Services are **discovered, not listed**: a directory under `services/` with both a `BUILD` file and a
`Dockerfile`. That is the entire contract, and it is why [[backstage]]'s scaffolder can add a service
without anyone editing CI. See [[paved-paths]].

[[pants]] does the same job inside the build system with `--tag=deployable`, and for the same reason —
a target declares itself deployable in the file that already describes it, rather than a shell pipeline
encoding a naming convention nothing checks.

## The loop guard is a consequence of the mono-repo

CI commits into the repo CI builds from, so without a guard every deploy triggers a build that triggers
a deploy, forever. Broken two ways, belt and braces: `[skip ci]` in the commit subject, and
`pipeline.sh` emitting a no-op when `HEAD` is already a `chore(deploy):` commit.

**With split app/config repos this problem simply does not exist** — which is the strongest practical
argument for splitting them, and worth more than the convenience the mono-repo bought (§2, §12.5).

## Why diff-scoping is not here

The obvious next step is `git diff --name-only` against the merge base, scoping the pipeline to what
changed. It does not fit, for two separate reasons, and the second is the important one:

- **Scoping builds breaks the deploy contract.** The overlay carries every tag and the deploy step
  rewrites all of them, so a skipped build stamps a SHA that was never pushed → `ImagePullBackOff`.
- **Scoping tests is worse, because it is silent.** Services are discovered from the filesystem, so
  every service gets an image whatever the tests did. Pair a diff-scoped test run with an unconditional
  image build and **you ship an image whose code was never tested on the commit that produced it** —
  the one outcome a pipeline exists to prevent. No step fails. It goes green.

**Diff-scoping is a matched pair or it is a hazard.** Fix the contract, then optimise the pipeline —
never the other way round.

## Related

[[buildkite]] · [[gitops]] · [[paved-paths]] · [[pants]] · [[order-platform]] · [[buildah]]

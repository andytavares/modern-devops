---
type: concept
tags: [ci, pipelines]
docs: https://buildkite.com/docs/pipelines/configure/dynamic-pipelines
date_added: 2026-08-15
date_updated: 2026-08-15
---

# Dynamic pipelines

> [!info] One-liner
> Generate the pipeline at the start of the build from a script, instead of committing a static YAML file.

## Why

`buildkite-agent pipeline upload` reads YAML on **stdin**, so the definition can be produced by a
script that knows things a static file cannot: which commit this is, what it changed, and whether the
build is worth running at all. In this project (§12.5) that bought three concrete things:

1. **The loop guard runs before any pod starts.** A `chore(deploy):` commit produces a one-step
   pipeline instead of running the full test-and-build cycle and discarding it.
2. **The per-service build steps stop being copy-paste.** They differed only by name; as hand-
   maintained twins they drift silently. One template in a `for` loop cannot.
3. **All `$$` escaping disappears.** The generator substitutes the SHA and registry as it writes, so
   the emitted YAML contains no `$` at all and upload-time interpolation has nothing to bite.

Plus the thing that makes [[paved-paths]] work: **services are discovered, not listed.** A directory
under `services/` with a Dockerfile in it is a service. That is the entire contract, which is why a
scaffolded service needs no pipeline edit.

## The price, and how to pay it

A YAML syntax error in a static pipeline is caught before the build runs; in a generated one it
appears mid-build. Mitigations, all in `.buildkite/upload.sh`:

- `pipeline upload --dry-run` first — rejects invalid YAML before any of it becomes steps
- `buildkite-agent artifact upload` the generated file — so the exact YAML that produced a weird build
  is attached to it
- **Don't pipe.** `generate | upload` takes the *last* command's exit status, so a generator that dies
  half-way still uploads whatever it printed and the step goes green. Write to a file under `set -e`.

## Gotchas specific to writing the generator

- **Quote your heredocs.** `<<'YAML'` passes text through; `<<YAML` interpolates. Get it wrong on a
  block containing `$$VAR` and `sh` expands `$$` to the **process ID** — you'll push an image tagged
  `8412REGISTRY` and lose an afternoon.
- Emit no literal `$` at all if you can avoid it: resolve values while writing the YAML.
- POSIX `sh` only — the default Buildkite agent image guarantees `/bin/sh`, not bash.

## Official docs

- Dynamic pipelines: https://buildkite.com/docs/pipelines/configure/dynamic-pipelines
- `pipeline upload`: https://buildkite.com/docs/agent/v3/cli-pipeline

> [!tip] Related
> [[buildkite]], [[paved-paths]], [[buildah]], [[immutable-image-tags]]

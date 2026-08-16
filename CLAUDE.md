# modern-devops — project schema

This repo holds a build-it-yourself DevOps platform tutorial and a **wiki** about every tool in it.
The wiki is the durable artifact: questions get answered *from* it, and answers that required
research get written *back* into it. It compounds. The tutorial does not.

## Layout

```
modern-devops-tutorial.md   # GENERATED from docs/. Do not edit. Regenerate with
                            #   python3 checks/build_single_edition.py . --write
docs/                       # THE SOURCE. Seven phases in build order, section-numbered (§N.M).
checks/                     # the tests that keep the docs honest (see rule 12)
  README.md                 # the map: seven phases, why that order, what each one ends with
  phase-N-*.md              # one file per phase; original §N.M numbering preserved
  appendices.md             # versions, troubleshooting, omissions, command reference
raw/                        # IMMUTABLE. Sources dropped by the human: doc excerpts, transcripts, links.
wiki/                       # CLAUDE-OWNED. Every file here is written and maintained by Claude.
  index.md                  # catalog of every page, grouped by role in the platform
  log.md                    # append-only record of every operation, newest last
  open-questions.md         # things we don't know yet, with what it would take to find out
  tools/                    # one page per tool, library or framework
  concepts/                 # one page per idea that spans tools (GitOps, mTLS, paved paths…)
.claude/skills/             # the three operations: ask, ingest, lint
```

## Rules

1. **Never modify `raw/`.** It is the immutable source layer.
2. **Never edit `modern-devops-tutorial.md` directly** — it is assembled from `docs/` and any edit is
   overwritten on the next regeneration. Change the phase file, then regenerate. And never modify it
   during a wiki operation: The tutorial changes only
   when the human asks for a tutorial change. If the wiki contradicts the tutorial, that is a
   finding to report, not a thing to silently fix.
3. **Always update `wiki/index.md` and `wiki/log.md`** after any operation that creates or changes a page.
4. **Cross-reference with `[[wikilinks]]`.** A page with no inbound and no outbound links is a bug.
5. **YAML frontmatter on every page**, matching the template in the page's own directory conventions.
6. **Cite.** Claims that come from the tutorial cite `§N.M`. Claims that come from vendor docs cite the
   URL. Claims that come from neither are labelled `unverified`.
7. **Flag contradictions with `> [!warning]`.** Never overwrite one claim with another silently —
   record both and say which source won and why.
8. **Date anything version-sensitive**: "as of 2026-08".
9. **Prefer updating an existing page over creating a near-duplicate.** Check `index.md` first.
10. **Kebab-case filenames**: `external-secrets-operator.md`.
11. **Uncertainty is content.** "We don't know whether X" belongs in `open-questions.md`, not in a
    confident sentence.
12. **The tutorial is a progressive build, and the war stories do not live in it.** Phase 1 shows
    `order-api` before gRPC exists; that is correct, and back-porting the end state would hand the
    reader code importing a service they have not built. A reader who follows phases 0-7 in order
    must end up holding this repo, with nothing failing on the first attempt. Defects found by
    running it are recorded in `wiki/` and in Appendix B — the phase text states the correct step
    and moves on. `checks/` enforces what it can: the single-file edition is assembled, every
    listing must name a real path, and a listing that shows a whole file must show the current one.

## Documentation lookup order

1. `wiki/` — do we already know this?
2. **Context7 MCP** (`resolve-library-id` → `query-docs`) — the canonical, current vendor docs.
3. `WebFetch` on the official docs URL recorded in the tool's page.
4. The tutorial, for how *this* platform uses it (which is not the same question as what the tool does).

Never answer a version, flag, or API-shape question from memory. Those are exactly the claims that rot.

## The loop

```
question ──▶ read index ──▶ read pages ──▶ enough?
                                 │              │ yes ──▶ answer with citations
                                 │              │ no  ──▶ research (Context7 → official docs)
                                 │                              │
                                 └──────────── write back ◀─────┘
                                        (page + index + log + open-questions)
```

The point of the write-back step: the same question is never researched twice.

## About the reader

Senior engineer, polyglot, works across many stacks. Wants blunt, direct, technically precise prose
with the tradeoffs stated. No hedging, no marketing language, no restating the question. If something
is a bad idea, say so and say why. If a claim is uncertain, mark it rather than smoothing it over.

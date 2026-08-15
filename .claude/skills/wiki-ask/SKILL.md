---
name: wiki-ask
description: >
  Answer a question about this project's platform, tooling or architecture using the project wiki,
  research anything the wiki cannot answer, then write the new knowledge back into the wiki so the
  same research never happens twice. Use whenever the user asks a question about any tool, library,
  framework, concept or design decision in this repo — Kubernetes, kind, Helm, Nexus, Floci, OpenBao,
  External Secrets, Kafka/Strimzi, Argo CD, Buildkite, Buildah, Prometheus, Grafana, Istio, Kiali,
  Backstage, FastAPI, Go, uv, Docker, containerd — or about how any of them fit together here. Also
  use for "wiki:", "ask the wiki", "what does the wiki say about X", "explain X", "why did we choose
  X", "how does X work", "what's the difference between X and Y", "should we use X", and for
  follow-up questions in an ongoing discussion about the stack. Prefer this over answering from
  memory: it is the mechanism by which this project's knowledge compounds.
---

# wiki-ask — question in, better wiki out

You are a sounding board with a memory. The user asks; you answer from the wiki, research the gaps,
and leave the wiki better than you found it. Read `CLAUDE.md` in the repo root for the schema and
rules — they are binding.

## The loop

### 1. Orient (always, cheaply)

Read `wiki/index.md`. It is the map. Pick the 1–4 pages most likely to hold the answer and read them.
Do not read the whole wiki. Do not read `modern-devops-tutorial.md` in full — it is ~4700 lines;
grep it for the section you need (`grep -n "§9.5" -A 30`) or read a specific line range.

If the question names a tool that has a page, read that page. If it spans tools, read the concept
page plus the two tool pages.

### 2. Decide: does the wiki already answer this?

Three outcomes, and you must be honest about which one you're in:

| State | What to do |
|---|---|
| **Covered** | Answer from the wiki. Cite pages as `[[page-name]]` and tutorial sections as `§N.M`. No research, no writes — say "already in the wiki" so the user knows the wiki earned its keep. |
| **Partial** | Answer what's covered, name precisely what's missing, research only that. |
| **Absent** | Research from scratch. |

Never pretend a gap is covered, and never re-research something a page already states. If a page
states something you doubt, that is a **contradiction to surface**, not a thing to quietly correct.

### 3. Research (only what's missing)

In this order:

1. **Context7 MCP** — `resolve-library-id` then `query-docs`. This is the canonical route for any
   library, framework, CLI or cloud service, and it beats web search for API shapes, flags,
   config keys and version-specific behaviour.
2. **WebFetch** on the official docs URL already recorded in the tool's page (`## Official docs`).
3. **WebSearch** only for things docs don't cover: release timing, ecosystem shifts, licence changes,
   "is this project still maintained".
4. **The repo itself** — `modern-devops-tutorial.md` for how *this* platform uses it. Note that
   "what does the tool do" and "what do we do with it here" are different questions with different
   sources; keep them separate in the answer.

Rules while researching:
- Never state a version, flag name, API shape or default from memory. Look it up.
- If two sources disagree, record both and say which you trust and why.
- If you cannot verify something, the answer says "unverified" and it goes in `open-questions.md`.

### 4. Answer

Lead with the answer. Then the reasoning, scaled to the question — a factual lookup gets two lines;
a design question gets the tradeoff. Cite as you go:

- `[[istio]]` for wiki pages
- `§9.6` for tutorial sections
- a bare URL for vendor docs

Be direct. If the user's premise is wrong, say so first and then answer the question they meant.

### 5. Write back — this is the part that makes it a wiki and not a chat

If step 3 produced anything the wiki didn't have, integrate it **before you finish the turn**:

- **Update the existing page** where it belongs. Prefer editing over creating.
- **Create a page** only if the subject is genuinely new — a tool or concept with no home. Match the
  frontmatter and section layout of a sibling page in the same directory.
- **Cross-reference**: add `[[wikilinks]]` both ways. A new page needs at least one inbound link from
  an existing page, or it is an orphan.
- **Update `wiki/index.md`** if you created a page or meaningfully changed what one covers.
- **Append to `wiki/log.md`** — one line, dated: what was asked, what changed, which pages.
- **Update `wiki/open-questions.md`** — remove anything you just answered; add anything you hit and
  could not resolve, with a note on what it would take to resolve it.

Then tell the user, in one or two lines, what the wiki gained. If nothing was learned, say that too —
"nothing new, this was already covered" is a good outcome.

## Scope discipline

- Answer the question asked. Don't write four pages because one was interesting.
- Don't edit `modern-devops-tutorial.md`. If research shows the tutorial is wrong, report it and let
  the user decide — a tutorial change is a tutorial task, not a wiki operation.
- Don't touch `raw/`.
- Rewriting a page wholesale is a red flag: if the page was that wrong, say so explicitly rather than
  quietly replacing it.

## Worked example

> **User:** "why does Prometheus scrape 15020 instead of the app port?"

1. Read `wiki/index.md` → `wiki/tools/istio.md`, `wiki/concepts/observability.md`.
2. `istio.md` covers merged metrics but doesn't say whether 15020 is exempt from STRICT mTLS or why.
3. Context7 → `/websites/istio_io` → query "merged metrics port 15020 and mTLS". Confirms the
   telemetry port and that securing it is opt-in (the 15091 task), i.e. plaintext by default.
4. Answer: the mechanism, why the alternatives are worse, cite `§9.6` and the docs URL.
5. Write back: add a "Ports" table to `istio.md`, link `[[prometheus]]` ⇄ `[[istio]]`, log it, and
   drop the now-answered line from `open-questions.md`.

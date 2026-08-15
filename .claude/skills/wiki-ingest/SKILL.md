---
name: wiki-ingest
description: >
  Add a new source, tool, library, framework or concept to this project's wiki. Use when the user
  drops a file into raw/, pastes a URL, article, doc excerpt, release note or repo link, or says
  "ingest this", "add this to the wiki", "wiki this", "note this", "add a page for X", "we're now
  using X", "log this decision", or introduces a tool the wiki has no page for. Also use after
  adopting or replacing a tool in the platform, so the wiki tracks what the stack actually is.
---

# wiki-ingest — source in, integrated page out

Turn a source into wiki knowledge that is linked, cited and findable. Read `CLAUDE.md` for the schema
and rules first — they are binding. The human curates sources; you do the bookkeeping.

## What counts as a source

| Source | Where it lands |
|---|---|
| A tool, library, framework, CLI | `wiki/tools/<kebab-name>.md` |
| An idea spanning tools (GitOps, mTLS, paved paths) | `wiki/concepts/<kebab-name>.md` |
| A URL, article, release note, doc excerpt | Save the *content* under `raw/`, then integrate into the pages it affects |
| A decision the user just made | The `## Why this, not the alternative` section of the affected tool page, plus a `log.md` line |

## Procedure

### 1. Read the source

If it is a file, read it. If it is a URL, `WebFetch` it. If it is a library the user named without a
link, go to **Context7** (`resolve-library-id` → `query-docs`) — that is the canonical route, not a
web search, and not your memory.

If the user pasted content worth keeping, write it to `raw/<kebab-name>.md` with a header recording
where it came from and when. **`raw/` is append-only: never edit or delete what's there.**

### 2. Check for a home before making one

Read `wiki/index.md`. If a page already covers this, **update it** — a second page on the same
subject is worse than a stale one. Only create when there is genuinely no home.

### 3. Write the page

Match the structure of a sibling page in the same directory (read one first — do not invent a new
layout). Every tool page carries:

```yaml
---
type: tool
tags: [...]
role: <the slot it fills in this platform>
version: <what the tutorial pins, or n/a>
docs: <official docs URL>
date_added: YYYY-MM-DD
date_updated: YYYY-MM-DD
status: in-use | evaluated | replaced | not-used
---
```

…followed by: one-liner → what it is → what it does *in this project* (with `§` refs and config
paths) → key concepts → why this and not the alternative → gotchas → official docs → open questions
→ related links.

Two rules that carry most of the value:

- **Separate "what it is" from "what we do with it."** Vendor capability and local usage are
  different claims with different sources and different rot rates.
- **Record the alternative that was rejected and why.** A page that only says what was chosen is
  half a page — the reasoning is what you'll want in six months when the constraint changes.

### 4. Verify every link

Every URL you add gets checked before you claim it:

```bash
curl -s -o /dev/null -w '%{http_code} %{url_effective}\n' -L <url>
```

`200` or a sane redirect. Anything else: fix it or drop it. Never ship a docs link you haven't
resolved — a dead link in a reference wiki is worse than no link.

### 5. Cross-reference, aggressively

Add `[[wikilinks]]` in both directions. Ask: what does this depend on, what depends on it, what does
it compete with, what concept does it instantiate? A new page with no inbound link is an orphan and
`wiki-lint` will flag it.

### 6. Update the bookkeeping

- `wiki/index.md` — add the page under the right grouping, with its one-line description.
- `wiki/log.md` — append one dated line: source, what changed, which pages.
- `wiki/open-questions.md` — add anything the source raised and didn't settle.

### 7. Report

Three lines, no more: what was created or updated, what it links to, what is still unknown.

## Anti-patterns

- Copying vendor marketing prose. Write what it *does* and what it *costs*, in the project's voice.
- A page that is a link dump. Links go in one section; the rest is your synthesis.
- Silently resolving a contradiction between a new source and an existing page. Flag it with
  `> [!warning]`, say which won, and why.
- Ingesting the same URL twice — check `raw/` and `log.md` first.

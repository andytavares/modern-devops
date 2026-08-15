---
name: wiki-lint
description: >
  Health-check the project wiki: find broken wikilinks, orphan pages, dead documentation URLs,
  versions that have drifted from the tutorial or from upstream, contradictions between pages,
  missing frontmatter, and stale claims. Use when the user says "wiki lint", "wiki health",
  "check the wiki", "wiki stats", "is the wiki still accurate", "what's stale", or after a batch of
  ingests. Also use before relying on the wiki for anything important.
---

# wiki-lint — keep it true

A reference wiki that is quietly wrong is worse than no wiki, because it is trusted. This skill finds
the rot. Read `CLAUDE.md` for the schema first.

## Checks

Run them in this order — cheap and mechanical first, expensive and judgement-based last.

### 1. Structural (scripted)

```bash
cd wiki

# Every [[wikilink]] resolves to a real page
grep -roh '\[\[[^]]*\]\]' . | tr -d '[]' | sort -u > /tmp/links.txt
find . -name '*.md' -exec basename {} .md \; | sort -u > /tmp/pages.txt
echo "--- broken wikilinks:"; comm -23 /tmp/links.txt /tmp/pages.txt

# Orphans: pages nothing links to. index/log/open-questions are entry points, not orphans.
echo "--- orphans:"
comm -13 /tmp/links.txt /tmp/pages.txt | grep -vE '^(index|log|open-questions)$'

# Frontmatter present on every page
echo "--- missing frontmatter:"
for f in tools/*.md concepts/*.md; do head -1 "$f" | grep -q '^---$' || echo "$f"; done

# Pages missing from the index
echo "--- not in index:"
for f in tools/*.md concepts/*.md; do
  n=$(basename "$f" .md); grep -q "\[\[$n\]\]" index.md || echo "$n"
done
```

### 2. Link rot

Every URL in the wiki, resolved:

```bash
grep -rhoE 'https?://[^ )>]+' wiki/ | sed 's/[.,]$//' | sort -u | while read -r u; do
  code=$(curl -s -o /dev/null -w '%{http_code}' -L --max-time 15 "$u")
  [ "$code" = "200" ] || echo "$code  $u"
done
```

Report anything that isn't `200`. `403` from a vendor bot-wall is usually fine — verify by hand
before deleting a link. `404` means the doc moved: find the new URL, don't just delete it.

### 3. Version drift

Three sources must agree, and when they don't, that's the finding:

1. `version:` in each tool page's frontmatter
2. the tutorial's **Appendix A — Version matrix**
3. what upstream actually publishes now

For the third, use the check command Appendix A already records for that component (`helm search
repo …`, a releases page, `curl` on the chart index). Report as a table: page / tutorial / upstream /
verdict. Do **not** edit the tutorial — version drift in the tutorial is a finding for the user, not
a fix for you.

### 4. Contradictions

Read `index.md`, then skim pages that cover overlapping ground (the tool page and its concept page;
two tools that compete). Look for claims that cannot both be true. Flag with `> [!warning]` on the
page, and report — do not silently pick a winner.

### 5. Staleness

Flag any page where:
- `date_updated` is more than ~3 months old **and** the tool has shipped a release since, or
- the page makes a time-sensitive claim ("as of 2026-08") that is now out of date, or
- `status:` says `in-use` for something the tutorial no longer uses (or vice versa).

## Fix policy

**Auto-fix without asking** — mechanical and safe:
- missing index entries
- missing/malformed frontmatter fields
- a wikilink whose target was obviously renamed
- `date_updated` when you actually changed the page

**Report, don't fix** — needs a human call:
- contradictions between pages
- version drift against upstream
- dead links where the replacement is ambiguous
- anything implying the tutorial itself is wrong

## Output

A short report, most-severe first:

```
wiki-lint — <date>
  pages: N tools, M concepts
  broken wikilinks: …
  dead links: …
  version drift: …
  contradictions: …
  stale: …
  auto-fixed: …
  needs your call: …
```

Then append one line to `wiki/log.md` recording the run and what was fixed.

If everything passes, say so in one line. Do not manufacture findings to look useful.

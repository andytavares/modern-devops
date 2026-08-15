# raw/ — immutable sources

Drop sources here: doc excerpts, release notes, articles, transcripts, pasted config, anything you
want the wiki to be built from.

**Nothing in this directory is ever edited or deleted, by Claude or by a skill.** It is the evidence
layer: the wiki is derived from it and can be regenerated, but a source is a record of what something
said at a point in time. If a source becomes wrong, add a newer one — don't rewrite history.

Convention: `<kebab-name>.md`, with a header recording where it came from and when.

```markdown
---
source: https://example.com/the-page
retrieved: 2026-08-15
---
```

`modern-devops-tutorial.md` in the repo root is the primary source and stays where it is; it is not
copied here.

# Wiki log

Append-only. Newest last. One entry per operation, recording what changed and why — not a changelog of
files, a record of what was learned.

---

- **2026-08-17** — **The wiki was rebuilt from scratch.** Every page under `tools/` and `concepts/`,
  plus `index.md`, `log.md` and `open-questions.md`, was deleted and rewritten against the current
  state of `docs/` and of the repository. The previous edition was **not** carried forward in any form;
  it remains in git history at `git show 376b4d8:wiki/log.md`. The risk was flagged before deleting —
  the old `log.md` held diagnoses that exist nowhere else — and the human confirmed a full rebuild.

  Method: all seven phase files and the appendices were read in full, then the repo itself —
  `pants.toml`, `3rdparty/python/requirements.txt`, the chart and its env overlay, `catalog-info.yaml`,
  `.buildkite/pipeline.sh`, `.buildkite/pants-ci.Dockerfile`, `go.mod`, `frontend/package.json`,
  `portal/backstage.json`, and the four scripts in `checks/`. No claim was carried over from the
  previous wiki without re-deriving it.

  **32 tool pages, 19 concept pages.** Against the previous edition's 29 and 11, the additions are:
  [[franz-go]], [[pydantic]], [[mypy]] (all three were load-bearing content previously buried inside
  other pages), and the concepts [[enterprise-substitution]], [[progressive-build]],
  [[dependency-inference]], [[cross-compilation]], [[port-naming]], [[health-checks]],
  [[timeouts-and-retries]] and [[at-least-once-delivery]]. Each of those eight had material spread
  across three or more tool pages with no single place stating the rule.

  Three things the rebuild surfaced, recorded in [[open-questions]] rather than fixed, because a wiki
  operation does not edit `docs/`:

  1. **Appendix A says Backstage `create-app` 1.53.1; `portal/backstage.json` says 1.53.0.**
  2. **Appendix A gives Helm as `≥3.8.0`; the CI image pins 4.2.4** — a major version the docs never
     mention.
  3. **Appendix A says Go 1.26.x; `go.mod` requires 1.26.5 and the CI image pins golang:1.26.6 with
     `GOTOOLCHAIN=local`.** Not a contradiction, but the patch-pinning is load-bearing and undocumented
     in Appendix A.

  One structural thing worth recording. The chart in the repo carries `pricing`, `frontend`,
  `podDisruptionBudget` and the `aws.*` credential keys that §10.1's listing does not, and
  `.buildkite/pipeline.sh` discovers services by `BUILD` + `Dockerfile` where §12.5 says `Dockerfile`
  alone. **Neither is drift.** `docs/` is a progressive build and `checks/verify_doc_listings.py`
  requires only the *last* listing of a file to match. That rule now has its own page,
  [[progressive-build]], because reading it as drift is the most likely way for a future
  operation to "fix" something correct.

- **2026-08-17** — **The wiki directory was renamed `wiki/` → `modern-devops-wiki/`**, so the Obsidian
  vault carries the project's name rather than a generic one. Obsidian takes the vault name from the
  directory name; there is no separate setting.

  Four reference sites had to move with it, and one of them is a docs edit:

  | File | Change |
  |---|---|
  | `pants.toml` | `pants_ignore` entry `"/wiki"` → `"/modern-devops-wiki"` |
  | `docs/phase-7-polyglot-monorepo.md` | the §17.3 listing of that same line |
  | `CLAUDE.md` | the layout tree and rules 3, 12 and the lookup order |
  | `.claude/skills/wiki-lint/SKILL.md` | `cd wiki` → `cd modern-devops-wiki`, plus path globs in all three skills |

  **The docs edit was unavoidable and is flagged here rather than made quietly.**
  `checks/verify_doc_listings.py` is a subsequence test, so leaving §17.3's listing saying `"/wiki",`
  after `pants.toml` stopped saying it would fail CI *and* leave the docs describing a directory that
  no longer exists. `modern-devops-tutorial.md` was regenerated with
  `python3 checks/build_single_edition.py . --write`; line count unchanged at 8539.

  The other `wiki` mentions in `docs/` were left alone deliberately: `docs/README.md` and §14.1's
  *"a wiki page titled How to add a service"* are generic prose about wikis, not references to this
  directory.

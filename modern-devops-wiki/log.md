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

- **2026-08-17** — **Asked: what is the CNI, in simple terms.** The wiki had **nothing** — no mention of
  CNI, kindnet, or pod networking anywhere in `modern-devops-wiki/`, `docs/` or `infra/`. Researched
  against kind's configuration docs via Context7 and confirmed against the repo.

  New page [[cni]], plus sections on [[kind]] and [[kubernetes]] and a caveat added to
  [[service-mesh]]. Verified facts: kind's default CNI is **`kindnetd`**, the default pod subnet is
  **`10.244.0.0/16`**, and `disableDefaultCNI: true` is the documented (advanced, limited-support)
  replacement path. `infra/kind-cluster.yaml` has no `networking:` block, so all defaults apply.

  **The finding worth having asked for:** `kindnetd` does not enforce NetworkPolicy, so Appendix C's
  "no NetworkPolicies" gap cannot be closed by writing one — the object would apply cleanly and do
  nothing. Closing it means replacing the CNI first. That is now stated on [[cni]] and cross-linked
  from [[service-mesh]], which previously said "use both" without noting that half of it is currently
  unavailable on this cluster.

- **2026-08-18** — **§3.2's `main_test.go` did not compile, and the checks could not see it.** Reported
  from an editor flagging `undefined: equalOffsets`. Reproduced by extracting the listings from the
  doc and building them against the real module: **eleven errors**, not one — `equalOffsets` was never
  shown anywhere, and `errors`, `context`, `dynamodb`, `ddbtypes` and `kgo` were used by a block whose
  only shown import set was `os` and `testing`.

  The cause was presentation: two consecutive blocks both labelled
  `**services/order-worker/main_test.go**`, the second starting mid-file at `var errWriteFailed`. The
  repo file was complete and correct the whole time.

  Fixed by making the second listing the **complete 209-line file**. A smaller patch — showing just
  the helper and the imports — does not work, and the reason is worth keeping: **`strings` is used by
  only one of the five tests, and Go rejects an unused import as hard as an undefined one**, so any
  abridgement that shows the real import block breaks a reader who stops before the last test. The
  file only compiles as a whole. Both listings were then verified by writing them to a scratch module
  and running `go test`: listing 1 passes, listing 2 passes.

  **The finding that outlives the bug:** `verify_doc_listings.py` is a subsequence test, so every line
  of the broken block *was* in the repo file in order and the check passed. It proves a listing is not
  stale; it proves nothing about whether the listing is sufficient. Now stated on
  [[progressive-build]] and cross-referenced from [[franz-go]]. Scanned the rest of `docs/` for the
  same shape — the only other repeated listings are the three order-api files, which are phase-1 →
  phase-7 progressive updates narrated as edits ("Add the imports and the metric to `main.py`") rather
  than presented as whole files, and Python does not fail on unused imports.

  Tutorial change, so `modern-devops-tutorial.md` was regenerated: 8539 → 8663 lines.
  `verify_doc_listings.py` still reports failures: 0.

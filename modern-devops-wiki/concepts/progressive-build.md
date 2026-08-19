---
type: concept
tags: [documentation, repo-structure]
date_added: 2026-08-17
date_updated: 2026-08-17
---

# The progressive build, and where the war stories live

> [!info] One-liner
> The tutorial is a build order, not a snapshot. Phase 1 shows `order-api` before gRPC exists, and that is correct. This wiki is where the failures go.

## The rule

A reader who follows phases 0–7 in order must end up holding this repo, **with nothing failing on the
first attempt.** Back-porting the end state would hand them code importing a service they have not
built.

So a listing in the docs is a snapshot of a *moment in the build*, and only the **last** listing of any
file, in build order, must match the repo. `checks/verify_doc_listings.py` enforces exactly that, with
a subsequence test, plus a rule that every bolded path a listing names must exist.

Concrete instances you will otherwise read as drift:

| The docs show | The repo has | Why both are right |
|---|---|---|
| §10.1 `values.yaml` with two services | five, plus PDBs and AWS credential keys | `pricing` and `frontend` arrive in Phase 7 |
| §12.5 service discovery keyed on `Dockerfile` | `BUILD` **and** `Dockerfile` | §19.5 tightens it once [[pants]] exists |
| §12.5 per-language test steps | one verify step | §19.5 replaces them |
| §3.1 `services/order-api/pyproject.toml` | deleted | §19.7 `git rm`s it, and the checker knows |
| §13.3 `serviceMonitor: enabled: true` | both monitors false by default | §9.6 swaps to `podMonitor` |

## What the checker cannot catch

`verify_doc_listings.py` does two things: every bolded path must exist, and the **last** listing of a
file must match the repo as a *subsequence* — every non-blank, non-elided line appearing in order.

That catches staleness. It cannot catch **incompleteness**, and the difference bit once: §3.2 showed
`main_test.go` twice, the second listing using `equalOffsets` and five imports that appeared in
neither block. Every line of it *was* in the repo file, in order, so the check passed while a reader
following the docs got eleven compile errors (fixed 2026-08-18 — see [[franz-go]]).

The general shape: **a subsequence test proves a listing is not out of date; it proves nothing about
whether the listing is enough.** For a compiled language "enough" means the file compiles, and the
only real check for that is compiling it. Worth knowing before trusting a green `checks/` run to mean
a reader can follow the text.

## Two editions, one source

`docs/` is the source. `modern-devops-tutorial.md` is **assembled** from it by
`checks/build_single_edition.py`, and `checks/test_docs_are_current.py` fails if the committed file
differs.

That machinery exists because the two were hand-maintained copies and drifted badly: **43 of 76 shared
sections had diverged, and 19 sections — all of §17–§19, the entire Pants/gRPC/frontend phase — existed
only in `docs/`.** Someone reading the single file built half a platform with no way to know.

The assembly is in **build order, not section-number order**, and that is deliberate: sorting by number
puts §9's STRICT mTLS before §10.5's "the pods come up 1/1 with no sidecar", and the document would
contradict itself. It is also why Phase 7 carries §17–§19 while sitting *before* Phase 6 in reading
order — the number records when it was built, the position records where it belongs.

## Where the failures go — this wiki

The tutorial reads as one linear path with no sidebars narrating problems. Twenty-three
`> [!warning]` callouts were removed from it, and each correct setting now appears **inline in the file
the reader writes**, with at most one sentence of justification.

The diagnostic content did not disappear. It lives in two places:

1. **Appendix B**, organised by **the symptom you see** rather than the component at fault — because at
   the point of failure you do not yet know the component.
2. **This wiki**, where a defect found by running the platform is recorded on the relevant tool page as
   a `> [!warning]` with the exact symptom.

> **That division is the reason this wiki exists.** The tutorial is the happy path made reliable; the
> wiki is the record of what it cost to make it reliable. Regenerating one from the other is not
> possible in either direction.

## The corollary for wiki operations

If the wiki contradicts the tutorial, **that is a finding to report, not a thing to silently fix**
(rule 2/7). Record both claims and say which source won and why. And the tutorial changes only when the
human asks for a tutorial change — never as a side effect of a wiki operation.

## Related

[[order-platform]] · [[pants]] · [[prometheus]] · [[uv]] · [[dynamic-pipelines]] · [[open-questions]]

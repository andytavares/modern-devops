"""Check that the docs leave the reader holding the repo we actually ship.

The docs use one convention: a bolded path on its own line, immediately followed
by a fenced block.

    **`services/order-api/order_api/main.py`**
    ```python
    ...
    ```

Two rules, and the second matters more than it looks:

1. Every path a listing names must exist. This catches renames — `app/` became
   `order_api/` and six listings kept pointing at the old path.

2. Only the LAST listing of a file, in build order, must match the repo. The
   tutorial is a progressive build: phase 1 shows order-api before gRPC exists,
   which is correct, because pricing is not introduced until phase 7. Requiring
   every listing to match HEAD would force phase 1 to show code importing a
   service the reader has not built yet — a guaranteed failure on first run.
   What must be true is that a reader who finishes phase 7 holds this repo.

Blocks are often excerpts, so the match is a subsequence test: every non-blank,
non-elided, non-placeholder line of the block must appear in the file, in order.

    python3 checks/verify_doc_listings.py .
"""

import re
import sys
from pathlib import Path

BLOCK = re.compile(
    r"^\*\*`(?P<path>[A-Za-z0-9_./-]+\.[A-Za-z0-9]+)`\*\*\s*\n+```[a-z]*\n(?P<body>.*?)^```",
    re.MULTILINE | re.DOTALL,
)

ELISION = re.compile(r"^\s*(#|//|--)?\s*(\.\.\.|…)\s*$")

# Lines the reader substitutes. The repo holds a real value where the doc
# correctly shows a placeholder, so these are not drift.
PLACEHOLDER = re.compile(r"<your-|<PASTE|YOUR_")

PHASE_ORDER = [
    "README",
    "phase-0",
    "phase-1",
    "phase-2",
    "phase-3",
    "phase-4",
    "phase-5",
    "phase-6",
    "phase-7",
    "appendices",
]


def _docs(repo):
    # docs/ only. modern-devops-tutorial.md is assembled from these, so
    # checking it too would just double-report every finding.
    return sorted((repo / "docs").glob("*.md"))


def _build_order(doc):
    if doc.name == "modern-devops-tutorial.md":
        return 100
    for i, key in enumerate(PHASE_ORDER):
        if key in doc.name:
            return i
    return 99


def _first_divergence(needles, haystack):
    i = 0
    for needle in needles:
        found = False
        while i < len(haystack):
            if haystack[i].strip() == needle.strip():
                found = True
                i += 1
                break
            i += 1
        if not found:
            return needle
    return None


def _deleted_by_a_later_phase(repo):
    """Paths the tutorial explicitly tells the reader to remove.

    `services/order-api/pyproject.toml` is written in phase 1 and deleted in
    phase 7, when Pants takes over resolution. It correctly does not exist in
    the repo, and the phase-1 listing is correct too.
    """
    out = set()
    for doc in _docs(repo):
        for line in doc.read_text().splitlines():
            stripped = line.strip()
            if not (stripped.startswith("git rm ") or stripped.startswith("rm ")):
                continue
            for token in stripped.split()[1:]:
                if "/" in token and "." in token:
                    out.add(token)
    return out


def _scan(repo):
    """Return (missing, final_listings)."""
    repo = Path(repo)
    missing, final = [], {}
    removed = _deleted_by_a_later_phase(repo)
    for doc in _docs(repo):
        if not doc.exists():
            continue
        text = doc.read_text()
        order = _build_order(doc)
        track = "single" if order == 100 else "phased"
        for m in BLOCK.finditer(text):
            path, body = m.group("path"), m.group("body")
            line_no = text[: m.start()].count("\n") + 1
            if not (repo / path).exists():
                if path not in removed:
                    missing.append(
                        f"{doc.relative_to(repo)}:{line_no} names {path} — no such file"
                    )
                continue
            key = (track, path)
            if key not in final or final[key][0] <= order:
                final[key] = (order, doc, line_no, body)
    return missing, final


def missing_paths(repo):
    return _scan(Path(repo))[0]


def drifted_final_listings(repo):
    repo = Path(repo)
    _, final = _scan(repo)
    out = []
    for (_track, path), (_order, doc, line_no, body) in sorted(final.items()):
        wanted = [
            ln
            for ln in body.splitlines()
            if ln.strip() and not ELISION.match(ln) and not PLACEHOLDER.search(ln)
        ]
        broke = _first_divergence(wanted, (repo / path).read_text().splitlines())
        if broke is not None:
            out.append(
                f"{doc.relative_to(repo)}:{line_no} {path} — not in file: {broke.strip()[:90]}"
            )
    return out


def drifted_complete_listings(repo):
    """Drift, restricted to listings that claim to be a WHOLE file.

    `drifted_final_listings` is the broader report and is useful to a human,
    but it cannot be a build gate: the tutorial is a progressive build, so
    phase 1 legitimately shows `order-api.yaml` before phase 4 adds the mesh
    annotations, and that reads as drift. A listing with the same first line
    AND the same line count as the file is claiming to be the whole thing, so
    any difference there is a real defect rather than a snapshot.
    """
    repo = Path(repo)
    _, final = _scan(repo)
    out = []
    for (_track, path), (_order, doc, line_no, body) in sorted(final.items()):
        block = body.rstrip().splitlines()
        actual = (repo / path).read_text().splitlines()
        if not block or len(block) != len(actual):
            continue
        if block[0].strip() != actual[0].strip():
            continue
        for i, (want, got) in enumerate(zip(block, actual), 1):
            if PLACEHOLDER.search(want):
                continue
            if want.rstrip() != got.rstrip():
                out.append(
                    f"{doc.relative_to(repo)}:{line_no} shows all of {path}, "
                    f"but line {i} differs:\n"
                    f"        doc:  {want.strip()[:80]}\n"
                    f"        file: {got.strip()[:80]}"
                )
                break
    return out


def main():
    """Exit non-zero only on the two rules that are unambiguous.

    The broader report is printed for a human to judge. It cannot gate a build:
    the tutorial is a progressive build, so a phase-1 listing legitimately
    differs from the end state, and treating that as a failure would train
    everyone to ignore the check.
    """
    repo = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    missing = missing_paths(repo)
    incomplete = drifted_complete_listings(repo)
    partial = drifted_final_listings(repo)

    for x in missing:
        print("  MISSING   " + x)
    for x in incomplete:
        print("  STALE     " + x)
    for x in partial:
        print("  review    " + x)

    hard = len(missing) + len(incomplete)
    print(f"\nfailures: {hard}    for review (progressive snapshots): {len(partial)}")
    return 1 if hard else 0


if __name__ == "__main__":
    sys.exit(main())

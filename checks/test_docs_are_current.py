"""The two editions of the tutorial must not be able to drift.

`modern-devops-tutorial.md` and `docs/` were maintained by hand as separate
copies: 43 of 76 shared sections had diverged, and 19 sections — all of
§17-§19, the entire Pants/gRPC/frontend phase — existed only in `docs/`.
Someone reading the single file built half a platform with no way to know.

So the single file is assembled from the phase docs rather than edited, and
this test is what makes that true rather than merely intended.

The other half of the guarantee — that every file listing still names a real
path and still matches the file — cannot run here. Pants tests are hermetic,
so the sandbox holds only declared dependencies, and a listing pointing at a
real repo file would read as missing. That check runs against the full
checkout in CI instead: `python3 checks/verify_doc_listings.py .`
"""

from pathlib import Path

from checks import build_single_edition as builder

REPO = Path(__file__).parent.parent


def test_single_file_edition_is_up_to_date():
    """Regenerate in memory; the committed file must already equal it."""
    generated = builder.assemble(REPO)
    committed = (REPO / "modern-devops-tutorial.md").read_text()
    assert committed == generated, (
        "modern-devops-tutorial.md is stale, or was edited directly. It is "
        "assembled from docs/ — edit the phase files, then regenerate:\n"
        "  python3 checks/build_single_edition.py . --write"
    )

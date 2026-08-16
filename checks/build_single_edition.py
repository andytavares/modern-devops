"""Assemble `modern-devops-tutorial.md` from the phased edition in `docs/`.

The two editions were maintained by hand and drifted badly: 43 of 76 shared
sections diverged, and 19 sections — all of §17-§19, the entire Pants/gRPC/
frontend phase — existed only in `docs/`. Someone reading the single file built
half a platform with no way to know.

So it is assembled, not maintained. `checks/test_docs_are_current.py` fails if
the committed file does not match what this produces.

    python3 checks/build_single_edition.py .           # report
    python3 checks/build_single_edition.py . --write
"""

import re
import sys
from pathlib import Path

HEADING = re.compile(r"^(#{2,4}) (\d+(?:\.\d+)?)\.? ([^\n]*)$", re.MULTILINE)

# Links between phase files become in-document anchors. The appendices stay a
# real file, because they are not part of the numbered build.
CROSS_LINK = re.compile(r"\]\(phase-\d+-[a-z-]+\.md(#[^)]*)?\)")


def split_sections(text):
    """Return (preamble, [(number, heading_line, body), ...])."""
    marks = list(HEADING.finditer(text))
    if not marks:
        return text, []
    out = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        out.append((m.group(2), text[m.start() : m.end()], text[m.end() : end]))
    return text[: marks[0].start()], out


def _sort_key(num):
    return [int(p) for p in num.split(".")] + [0]


def assemble(repo: Path) -> str:
    """Build the single-file edition. Pure function of the repo's docs."""
    repo = Path(repo)
    target = repo / "modern-devops-tutorial.md"
    single_pre, single_secs = split_sections(target.read_text())
    single_by_num = {n: (h, b) for n, h, b in single_secs}

    # BUILD order, not numeric order. The numbers name the topic; the phases
    # name the sequence, and the prose states what is true at that point in the
    # build. §10.5 says the pods come up 1/1 with no sidecar, which holds only
    # before §9 turns the mesh on — so §10 is emitted before §9, and sorting
    # this file by number would make it contradict itself.
    ordered, seen = [], set()
    for doc in sorted((repo / "docs").glob("phase-*.md")):
        _, secs = split_sections(doc.read_text())
        for n, h, b in secs:
            ordered.append((n, (h, b, doc.name)))
            seen.add(n)

    # Front-matter sections that exist only in the single-file edition lead.
    lead = [
        (n, (h, b, "modern-devops-tutorial.md"))
        for n, (h, b) in single_by_num.items()
        if n not in seen
    ]
    ordered = sorted(lead, key=lambda kv: _sort_key(kv[0])) + ordered

    parts = [single_pre.rstrip() + "\n\n"]
    for _num, (heading, body, _src) in ordered:
        parts.append(heading + "\n")
        parts.append(body.rstrip() + "\n\n")

    # Appendices come from docs/appendices.md so the troubleshooting table has
    # exactly one source.
    app_text = (repo / "docs" / "appendices.md").read_text()
    tail = re.search(r"^## Appendix A", app_text, re.MULTILINE)
    if tail:
        parts.append("---\n\n" + app_text[tail.start() :].rstrip() + "\n")

    out = "".join(parts)
    out = CROSS_LINK.sub(lambda m: "](" + (m.group(1) or "#") + ")", out)
    out = out.replace("](appendices.md", "](docs/appendices.md")
    out = out.replace("](README.md", "](docs/README.md")
    return re.sub(r"\n{4,}", "\n\n\n", out)


def main():
    repo = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    target = repo / "modern-devops-tutorial.md"
    generated = assemble(repo)
    current = target.read_text()
    print(f"lines: {len(current.splitlines())} -> {len(generated.splitlines())}")
    if "--write" in sys.argv:
        target.write_text(generated)
        print(f"wrote {target.name}")
        return 0
    print("up to date" if current == generated else "STALE — rerun with --write")
    return 0 if current == generated else 1


if __name__ == "__main__":
    sys.exit(main())

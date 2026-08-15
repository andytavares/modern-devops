# Log

Append-only. Newest last. One line per operation: date — what happened — pages touched.

---

- **2026-08-15** — Wiki created from `modern-devops-tutorial.md`. 24 tool pages, 11 concept pages,
  index, open questions. Every documentation URL verified with `curl` (all 200). Skills added:
  `wiki-ask`, `wiki-ingest`, `wiki-lint`. Schema written to `CLAUDE.md`.
- **2026-08-15** — `uv run pytest -q` failed building `pydantic-core` 2.33.2. Root cause: unpinned
  interpreter (`requires-python = ">=3.13"`, no `.python-version`) → uv chose Homebrew's 3.14.7 →
  no cp314 wheel → source build → pyo3 0.24.1 caps at 3.13. Fixed by `uv python pin 3.13` +
  `requires-python = ">=3.13,<3.14"`; venv rebuilt on 3.13.15, **8 tests pass, ruff clean**. Same
  latent defect fixed in the tutorial (§3.1) with a new callout. Pages: [[uv]] (new pinning section
  + verified wheel facts), [[fastapi]] (cross-link).


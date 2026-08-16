python_sources(
    name="lib",
    # Everything that is not a test. `verify_chart.py` is not imported by the
    # test suite — it runs in CI against a rendered chart — but it still needs
    # an owning target, or `pants tailor --check` reports the file as unowned.
    sources=["*.py", "!test_*.py"],
)

python_tests(
    name="tests",
    sources=["test_*.py"],
    # Prose read as plain text. Nothing here is reachable by import, which is
    # exactly why the two editions of the tutorial were free to drift apart.
    dependencies=[
        ":lib",
        "docs:docs",
        "//:single-edition",
    ],
)

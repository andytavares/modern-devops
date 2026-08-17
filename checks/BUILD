python_sources(
    name="lib",
    sources=["build_single_edition.py", "verify_doc_listings.py"],
)

python_tests(
    name="tests",
    sources=["test_*.py"],
    # Config and prose read as plain text from three other directories. None of
    # it is reachable by import, which is exactly why these files were free to
    # drift apart in the first place.
    dependencies=[
        ":lib",
        "frontend:nginx_conf",
        "deploy/charts/order-platform:order-api-template",
        "docs:docs",
        "//:single-edition",
    ],
)

python_tests(
    name="tests",
    sources=["test_*.py"],
    # Config files from two other directories, read as plain text. Nothing
    # infers these — there is no import to follow, which is exactly why the two
    # were free to drift apart in the first place.
    dependencies=[
        "frontend:nginx_conf",
        "deploy/charts/order-platform/templates:order-api-template",
    ],
)

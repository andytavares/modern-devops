python_sources(
    name="lib",
    sources=["order_api/**/*.py"],
)

python_tests(
    name="tests",
    # `!tests/__init__.py`: it's a namespace marker, not a test — including it
    # makes Pants generate a `python_test` target for it that pytest then fails
    # with "no tests collected".
    sources=["tests/**/*.py", "!tests/__init__.py"],
    # The `app` top-level package name collides with pricing's own `app` package
    # under the shared `/services/*` source root, so dependency inference can't
    # disambiguate `from order_api.main import ...` on its own.
    dependencies=[":lib"],
)

pex_binary(
    name="bin",
    entry_point="order_api.main:main",
    dependencies=[":lib"],
    # The cluster runs linux/aarch64, not this macOS laptop. Without this,
    # `pants package` resolves macOS wheels for native deps (grpcio,
    # pydantic-core, uvloop, watchfiles) that import-fail in the container.
    complete_platforms=["3rdparty/python:linux-platform"],
)

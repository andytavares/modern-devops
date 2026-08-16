# A scaffolded service is a first-class member of the Pants monorepo. Without
# this file CI would not build it at all — service discovery in
# .buildkite/pipeline.sh keys off services/*/BUILD, and a directory Pants does
# not know about cannot be linted, typechecked, tested or packaged. The failure
# would be silent: the pipeline would simply not mention the new service.
python_sources(
    name="lib",
    sources=["${{ values.name | replace('-', '_') }}/**/*.py"],
)

python_tests(
    name="tests",
    sources=["tests/**/*.py", "!tests/__init__.py"],
    # Explicit because several services could otherwise satisfy this import.
    dependencies=[":lib"],
)

pex_binary(
    name="bin",
    entry_point="${{ values.name | replace('-', '_') }}.main:main",
    dependencies=[":lib"],
    # The cluster runs linux/arm64. Without this, a PEX built on a macOS
    # laptop resolves macOS wheels, passes every check, and dies on import
    # inside the container. See 3rdparty/python/BUILD.
    complete_platforms=["3rdparty/python:linux-platform"],
    # dist/ is the Buildah build context; the Dockerfile COPYs by this name.
    output_path="${{ values.name }}.pex",
)

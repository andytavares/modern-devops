# syntax=docker/dockerfile:1.7
#
# The build now happens under Pants (`pants package services/order-worker:bin`),
# not here. This Dockerfile's build context is Pants' dist/ output (dist/,
# where the go_binary's output_path lands the artifact at dist/order-worker)
# rather than this source tree — the binary is already compiled, static
# (CGO_ENABLED=0 is set by the Go backend's default toolchain env), and
# stripped.
#
# Version stamping: Pants' go_binary supports `linker_flags` (i.e. -ldflags),
# but there is no `main.version` package variable left to -X inject into —
# main.go reads SERVICE_VERSION from the environment at startup, defaulting to
# "dev". So the old --build-arg VERSION=$SHA is gone; set SERVICE_VERSION at
# deploy time (e.g. in the Kubernetes manifest env) instead.
FROM gcr.io/distroless/static-debian12:nonroot
# --chmod is required, not cosmetic. `pants package` writes an executable
# binary, but the verify step uploads it as a Buildkite artifact and the build
# step downloads it — and artifact transfer does not preserve file modes. The
# bit is lost between the two pods, and the failure is not a build error but a
# runtime one, with no application output at all:
#   exec: "/order-worker": permission denied
# The PEX services are immune only because they are invoked as
# `python /app/x.pex` rather than executed directly.
COPY --chmod=0755 order-worker /order-worker
USER 65532:65532
EXPOSE 9090
ENTRYPOINT ["/order-worker"]
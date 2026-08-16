# syntax=docker/dockerfile:1.7
#
# The CI image for the verify step. Built once by hand and pushed to Nexus:
#
#   buildah bud --file .buildkite/pants-ci.Dockerfile -t nexus:8082/ci/pants:0.13.2 .
#   buildah push nexus:8082/ci/pants:0.13.2
#
# That builds for the host's architecture. The Dockerfile also builds for the
# other one — pass `--platform linux/amd64` (or linux/arm64) if the machine you
# build on and the nodes you run on disagree.
#
# Why an image rather than installing Pants in the step:
#
# Pants 2.x is NOT on PyPI. `pip install pantsbuild.pants==2.33.0` fails —
# the package stops at 2.18 on the public index and 2.9.2 upstream, because
# modern Pants ships only as the scie-pants launcher binary.
#
# The launcher has to come from GitHub, which is outside the §5.1 choke point.
# Fetching it once, verifying its published checksum, and baking it into an
# image that lives in Nexus is the honest compromise: every CI run pulls from
# Nexus, and the one unproxied download is explicit, pinned and verified rather
# than repeated on every build.
FROM docker.io/library/python:3.13-slim

# Multi-arch. Readers run this on both x86_64 laptops/runners and Apple
# silicon, and a single-arch image fails the other half with a bare
# `Exec format error`.
#
# TARGETARCH is the automatic build ARG BuildKit sets from the build platform
# ("amd64" / "arm64"):
#   https://docs.docker.com/reference/dockerfile/#automatic-platform-args-in-the-global-scope
# It has to be re-declared per stage to be visible, and the legacy (non-BuildKit)
# builder does not set it at all — hence the `dpkg --print-architecture`
# fallback below, which uses the identical Debian vocabulary and, under
# buildx + QEMU, runs on the target platform and so reports the target arch.
ARG TARGETARCH

# Pants ships as the scie-pants launcher, one binary per arch, each with a
# published .sha256. Both are pinned here rather than fetched at build time.
#
# NOT `curl https://static.pantsbuild.org/setup/get-pants.sh | bash`, which the
# Pants docs offer for workstations: it downloads `${url}.sha256` from the same
# origin it downloads the binary from and verifies one against the other. That
# catches a corrupted transfer; it cannot catch a compromised release, because
# an attacker who can replace the artifact can replace the checksum beside it.
# It also defaults to the *latest* version and installs into ${HOME}/.local/bin
# — and HOME is /tmp in this image. Pinning the value we reviewed keeps the
# supply-chain property the comment above actually claims.
ARG SCIE_PANTS_VERSION=0.13.2
ARG SCIE_PANTS_SHA256_AMD64=74a1e53bc50d6ef6ce1bc67bd9f7b48e549505e0a2453ad4d5ccbc72b0bea874
ARG SCIE_PANTS_SHA256_ARM64=b40b60e50e9cb69e13029e100be995fbfdb3b3799ef1ccff60a81177f78e6b82

# Helm is here so CI can validate the chart. `helm lint --strict` and
# `helm template` are the two commands Helm documents for exactly that, and
# without them nothing in the build ever renders the chart — a template that
# fails to render, or a probe naming a port no container declares, reaches the
# cluster before anyone finds out.
#
# Per-arch tarball, per-arch checksum, both from
# https://get.helm.sh/helm-v${HELM_VERSION}-linux-${arch}.tar.gz.sha256sum
ARG HELM_VERSION=4.2.4
ARG HELM_SHA256_AMD64=c306b46f719b0a4da32d0f78ee21bf90ce8d602f15b22ab753f0674d1670a7f3
ARG HELM_SHA256_ARM64=564de2191b881e9f71b5606b25345821ea1682f06ab90499d3ab22b530176da1

# unzip/zip/xz are here because Pants unpacks the tools it downloads (protoc,
# ruff, the Go SDK) and fails with a bare BinaryNotFoundError without them.
# gcc/g++ are here because confluent-kafka-go wraps librdkafka, which needs
# cgo. Pants does NOT download a Go toolchain — [golang].go_search_paths only
# *searches* — so Go has to be in the image or `pants lint ::` dies with
# "Cannot find any `go` binaries".
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      ca-certificates curl git build-essential \
      unzip zip xz-utils \
 && rm -rf /var/lib/apt/lists/*

# Go from the official image rather than Debian's, so the version matches
# services/order-worker/go.mod exactly.
#
# The patch version is pinned, not just the minor. go.mod says `go 1.26.5` and
# GOTOOLCHAIN=local below forbids downloading a newer toolchain, so a floating
# `golang:1.26` that ever resolves below 1.26.5 turns every Go build into
# "go.mod requires go >= 1.26.5 (running go 1.26.N)". The tag is multi-arch, so
# this resolves to the build's target platform on its own.
COPY --from=docker.io/library/golang:1.26.6 /usr/local/go /usr/local/go
ENV PATH="/usr/local/go/bin:${PATH}" \
    GOTOOLCHAIN=local

# Checksum-verified. A binary pulled off the internet and executed in CI without
# one is a supply-chain hole no amount of proxying elsewhere makes up for. The
# arch selects *which* pinned checksum applies; it never selects whether one does
# — an unrecognised TARGETARCH is a build failure, not an unverified download.
RUN set -eu; \
    arch="${TARGETARCH:-$(dpkg --print-architecture)}"; \
    case "$arch" in \
      amd64) suffix=x86_64;  sha="${SCIE_PANTS_SHA256_AMD64}" ;; \
      arm64) suffix=aarch64; sha="${SCIE_PANTS_SHA256_ARM64}" ;; \
      *) echo "unsupported architecture: $arch" >&2; exit 1 ;; \
    esac; \
    curl -fsSL -o /usr/local/bin/pants \
      "https://github.com/pantsbuild/scie-pants/releases/download/v${SCIE_PANTS_VERSION}/scie-pants-linux-${suffix}"; \
    echo "${sha}  /usr/local/bin/pants" | sha256sum -c -; \
    chmod 755 /usr/local/bin/pants

RUN set -eu; \
    arch="${TARGETARCH:-$(dpkg --print-architecture)}"; \
    case "$arch" in \
      amd64) sha="${HELM_SHA256_AMD64}" ;; \
      arm64) sha="${HELM_SHA256_ARM64}" ;; \
      *) echo "unsupported architecture: $arch" >&2; exit 1 ;; \
    esac; \
    curl -fsSL -o /tmp/helm.tgz \
      "https://get.helm.sh/helm-v${HELM_VERSION}-linux-${arch}.tar.gz"; \
    echo "${sha}  /tmp/helm.tgz" | sha256sum -c -; \
    tar -xzf /tmp/helm.tgz -C /tmp; \
    install -m 0755 "/tmp/linux-${arch}/helm" /usr/local/bin/helm; \
    rm -rf /tmp/helm.tgz "/tmp/linux-${arch}"

# pyyaml is for checks/verify_chart.py, which parses the rendered chart. It
# comes from the Nexus proxy like everything else — see §5.1.
RUN pip install --no-cache-dir \
      --index-url http://nexus:8081/repository/pypi-proxy/simple \
      --trusted-host nexus \
      pyyaml==6.0.2

# Pants resolves its own Python and tools at runtime; give it a writable home.
ENV HOME=/tmp
WORKDIR /workspace

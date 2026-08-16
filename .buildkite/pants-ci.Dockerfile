# syntax=docker/dockerfile:1.7
#
# The CI image for the verify step. Built once by hand and pushed to Nexus:
#
#   buildah bud --file .buildkite/pants-ci.Dockerfile -t nexus:8082/ci/pants:0.13.2 .
#   buildah push nexus:8082/ci/pants:0.13.2
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

ARG SCIE_PANTS_VERSION=0.13.2
ARG SCIE_PANTS_SHA256=b40b60e50e9cb69e13029e100be995fbfdb3b3799ef1ccff60a81177f78e6b82

# Helm is here so CI can validate the chart. `helm lint --strict` and
# `helm template` are the two commands Helm documents for exactly that, and
# without them nothing in the build ever renders the chart — a template that
# fails to render, or a probe naming a port no container declares, reaches the
# cluster before anyone finds out.
ARG HELM_VERSION=4.2.4
ARG HELM_SHA256=564de2191b881e9f71b5606b25345821ea1682f06ab90499d3ab22b530176da1

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
# services/order-worker/go.mod (1.26.x) exactly.
COPY --from=docker.io/library/golang:1.26 /usr/local/go /usr/local/go
ENV PATH="/usr/local/go/bin:${PATH}" \
    GOTOOLCHAIN=local

# Checksum-verified. A binary pulled off the internet and executed in CI without
# one is a supply-chain hole no amount of proxying elsewhere makes up for.
RUN curl -fsSL -o /usr/local/bin/pants \
      "https://github.com/pantsbuild/scie-pants/releases/download/v${SCIE_PANTS_VERSION}/scie-pants-linux-aarch64" \
 && echo "${SCIE_PANTS_SHA256}  /usr/local/bin/pants" | sha256sum -c - \
 && chmod 755 /usr/local/bin/pants

RUN curl -fsSL -o /tmp/helm.tgz \
      "https://get.helm.sh/helm-v${HELM_VERSION}-linux-arm64.tar.gz" \
 && echo "${HELM_SHA256}  /tmp/helm.tgz" | sha256sum -c - \
 && tar -xzf /tmp/helm.tgz -C /tmp \
 && install -m 0755 /tmp/linux-arm64/helm /usr/local/bin/helm \
 && rm -rf /tmp/helm.tgz /tmp/linux-arm64

# pyyaml is for checks/verify_chart.py, which parses the rendered chart. It
# comes from the Nexus proxy like everything else — see §5.1.
RUN pip install --no-cache-dir \
      --index-url http://nexus:8081/repository/pypi-proxy/simple \
      --trusted-host nexus \
      pyyaml==6.0.2

# Pants resolves its own Python and tools at runtime; give it a writable home.
ENV HOME=/tmp
WORKDIR /workspace

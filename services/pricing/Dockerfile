# syntax=docker/dockerfile:1.7
#
# Build context is `dist/` (the `pants package services/pricing:bin` output),
# not the source tree: the PEX already bundles the interpreter-independent
# dependency closure resolved by Pants from locks/python-default.lock, so there
# is nothing left for this image to resolve or install.
FROM docker.io/library/python:3.13-slim

RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin appuser

WORKDIR /app
COPY --chown=10001:10001 pricing.pex /app/pricing.pex

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER 10001
# 50051 gRPC, 9090 the health/metrics HTTP server.
EXPOSE 50051 9090
ENTRYPOINT ["python", "/app/pricing.pex"]

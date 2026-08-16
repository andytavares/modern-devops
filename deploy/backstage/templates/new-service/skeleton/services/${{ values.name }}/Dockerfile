# syntax=docker/dockerfile:1.7
#
# Build context is `dist/` — the output of `pants package`, not this source
# tree. The PEX already carries the whole dependency closure resolved from
# locks/python-default.lock, so there is nothing for this image to install.
FROM docker.io/library/python:3.13-slim

RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin appuser

WORKDIR /app
COPY --chown=10001:10001 ${{ values.name }}.pex /app/service.pex

# A PEX unpacks its dependency closure on first run, so it needs somewhere
# writable. Under readOnlyRootFilesystem it has nowhere and dies in the PEX
# bootstrap before any application log line appears. The chart mounts an
# emptyDir at /tmp to match.
ENV PEX_ROOT=/tmp/pex \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER 10001
EXPOSE 8000
ENTRYPOINT ["python", "/app/service.pex"]

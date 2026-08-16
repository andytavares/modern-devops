#!/bin/sh
# Emits this build's pipeline as YAML on stdout. It talks to nothing and
# changes nothing - run it locally and read what it prints.
#
# POSIX sh, deliberately: this runs in the default agent image, whose only
# guaranteed shell is /bin/sh.
set -eu

REGISTRY="nexus:8082"
# A build triggered by hand in the UI sets BUILDKITE_COMMIT to the literal
# string "HEAD" rather than a SHA, which would tag images `:HEAD` — a mutable
# tag that means a different image on every build, and the exact thing §10.3
# says a tag must never be. Resolve it to a real SHA before it reaches a tag.
if [ "$BUILDKITE_COMMIT" = "HEAD" ]; then
  BUILDKITE_COMMIT="$(git rev-parse HEAD)"
fi
SHA="$(echo "$BUILDKITE_COMMIT" | cut -c1-12)"

case "$SHA" in
  *[!0-9a-f]*|"") echo "refusing to build: BUILDKITE_COMMIT is not a SHA ($BUILDKITE_COMMIT)" >&2; exit 1 ;;
esac

# Services are discovered, not listed. A directory under services/ with a
# BUILD file in it is a service, and that is the entire contract. This is what
# lets the Backstage paved path (§14.6) add a service without touching CI.
#
# BUILD is the signal rather than Dockerfile alone: a directory Pants does not
# know about cannot be built, tested or packaged, so it is not a service this
# pipeline can deliver.
SERVICES="$(cd services && ls -d */ 2>/dev/null | sed 's#/##' | while read -r s; do
  [ -f "$s/BUILD" ] && [ -f "$s/Dockerfile" ] && echo "$s"
done | sort | tr '\n' ' ')"

if [ -z "$SERVICES" ]; then
  echo "no services found under services/*/Dockerfile" >&2
  exit 1
fi

# ── LOOP GUARD ─────────────────────────────────────────────────────────────
# The deploy step at the bottom commits into the repo we build from, so
# without this every deploy triggers a build that makes another deploy,
# forever. Deciding it here, before any step exists, is the whole reason this
# is a script.
if git log -1 --pretty=%s | grep -q '^chore(deploy):'; then
  cat <<'YAML'
steps:
  - label: ":fast_forward: deploy commit, nothing to build"
    agents: { queue: kubernetes }
    command: "echo 'HEAD is a deploy commit; skipping'"
YAML
  exit 0
fi

# ── Header ─────────────────────────────────────────────────────────────────
# Every step runs in its own Kubernetes pod, created by agent-stack-k8s.
# The `kubernetes` plugin is how a step describes the pod it wants.
cat <<'YAML'
env:
  # Nexus proxies. Builds never talk to pypi.org or proxy.golang.org directly:
  # that is the supply-chain choke point from §5.1, made real.
  # pip needs these to install uv itself. uv does NOT get its index from here:
  # it reads [[tool.uv.index]] in services/order-api/pyproject.toml, so the
  # registry is recorded in uv.lock and `--locked` validates the same way on a
  # laptop and in this pod. Setting UV_DEFAULT_INDEX here instead would put the
  # index in CI only, and the committed lock would never match it.
  PIP_INDEX_URL: "http://nexus:8081/repository/pypi-proxy/simple"
  PIP_TRUSTED_HOST: "nexus"
  GOPROXY: "http://nexus:8081/repository/go-proxy"
  # Nothing disables checksum verification. go.sum records a hash for every
  # module in the build list, so the go command verifies against it locally and
  # never reaches for the checksum database. GOSUMDB=off would not help here —
  # it would only disarm verification for the next dependency added.
  GOFLAGS: "-mod=readonly"

steps:
  # ── 1. One step, every language ──────────────────────────────────────────
  # One invocation covers every language, and it discovers what changed and
  # what depends on it. Adding a service does not mean editing this step.
  #
  # `pants package` runs here too, rather than in the image build, because the
  # build steps below are daemonless Buildah pods with no toolchain: no Python,
  # no Go, no Node. They receive artifacts, they do not produce them.
  - label: ":hammer: lint · typecheck · test · package"
    key: verify
    agents: { queue: kubernetes }
    artifact_paths: "dist/*"
    plugins:
      - kubernetes:
          podSpec:
            # The pants image lives in Nexus, which requires auth. nexus-push is
            # Opaque (a Buildah auth file) and the kubelet cannot use it here.
            imagePullSecrets:
              - name: nexus-pull
            containers:
              # Built once from .buildkite/pants-ci.Dockerfile and pushed to
              # Nexus. Pants 2.x is NOT on PyPI — `pip install
              # pantsbuild.pants==2.33.0` fails, because modern Pants ships
              # only as the scie-pants launcher binary. Baking that binary
              # into an image keeps every build pulling from Nexus.
              - image: nexus:8082/ci/pants:0.13.2
                resources:
                  requests: { cpu: "1", memory: 2Gi }
                  limits:   { memory: 4Gi }
                command:
                  - |
                    set -euo pipefail

                    # git metadata: Pants uses it to decide what changed.
                    git config --global --add safe.directory "$PWD"

                    pants lint check test ::

                    # Runs here rather than as a Pants test because it reads
                    # the whole checkout: every file listing in docs/ must
                    # still name a real path, and a listing that shows an
                    # entire file must show the current one. A Pants sandbox
                    # only holds declared dependencies, so every listing would
                    # read as missing there.
                    python3 checks/verify_doc_listings.py .

                    # `--tag` is Pants' documented way to select a subset of
                    # targets. Every deployable target declares `deployable` in
                    # its BUILD file, so a service the Backstage paved path
                    # (§14.6) adds is packaged the moment it declares itself —
                    # no list here to forget to update, and no naming
                    # convention enforced outside the build system.
                    pants --tag=deployable package ::

                    ls -la dist/

  - wait
YAML

# `golang:1.26` and not `golang:1.26-alpine` for the TEST step specifically:
#
#   golang:1.26-alpine : CGO_ENABLED=0, no gcc
#   golang:1.26        : CGO_ENABLED=1, gcc 14.2.0, git 2.47.3
#
# `go test -race` is implemented with a C runtime, so on alpine it refuses with
# `go: -race requires cgo; enable cgo by setting CGO_ENABLED=1` — and setting
# that variable alone doesn't help, because there is no compiler to use. The
# Dockerfile in §3.2 still builds FROM golang:1.26-alpine, and should: there we
# *want* CGO_ENABLED=0 for a static binary in a scratch image. Test and build
# want opposite things from the same toolchain, which is why they differ.

# ── 2. Build and push images ───────────────────────────────────────────────
# These pods contain Buildah and nothing else — no Python, no Go, no compiler.
# They download the artifact the verify step produced and copy it into an
# image. That is the whole reason `pants package` runs upstream rather than
# here, and it is why every Dockerfile in services/ is now four lines long.
#
# The build context is dist/, not the service directory, because that is where
# the artifacts are. Each Dockerfile COPYs its artifact by name (order-api.pex,
# pricing.pex, order-worker), which is what the `output_path` on each Pants
# target exists to guarantee.
for SVC in $SERVICES; do
  # No build args. Version reaches the binary through SERVICE_VERSION in the
  # environment, which the Helm chart sets — not through the linker.

  cat <<YAML

  - label: ":docker: build $SVC ($SHA)"
    key: build-$SVC
    agents: { queue: kubernetes }
    plugins:
      - kubernetes:
          podSpec:
            volumes:
              - name: nexus-auth
                secret: { secretName: nexus-push }
            containers:
              - image: quay.io/buildah/stable:v1.40.1
                # See the securityContext note below. This is a real trade.
                securityContext:
                  privileged: true
                env:
                  - name: STORAGE_DRIVER
                    value: vfs
                  - name: BUILDAH_FORMAT
                    value: docker
                  - name: REGISTRY_AUTH_FILE
                    value: /auth/config.json
                volumeMounts:
                  - name: nexus-auth
                    mountPath: /auth
                    readOnly: true
                command:
                  - |
                    set -euo pipefail

                    # The artifact built by the verify step. Without this the
                    # COPY below fails with "no such file or directory" on a
                    # path that exists perfectly well in the repo — because the
                    # context is dist/, not the source tree.
                    buildkite-agent artifact download "dist/*" .
                    ls -la dist/

                    # --tls-verify=false exists only because §5.8 runs Nexus
                    # on plain HTTP. It disables certificate verification on a
                    # connection that carries push credentials. Behind real TLS
                    # you delete the flag and mount the CA instead — it is not
                    # a Buildah setting you keep.
                    buildah bud \\
                      --tls-verify=false \\
                      --file services/$SVC/Dockerfile \\
                      --tag "$REGISTRY/shop/$SVC:$SHA" \\
                      dist

                    buildah push --tls-verify=false "$REGISTRY/shop/$SVC:$SHA"

                    echo "pushed $REGISTRY/shop/$SVC:$SHA"
YAML
done

# The frontend is not under services/ and does not consume a Pants artifact:
# its Dockerfile runs the vite build itself in a node stage. That is a
# deliberate inconsistency — the static bundle is platform-independent, so it
# has none of the cross-compilation problem that forced the other three into
# the artifact-handoff shape. Worth revisiting if the node stage gets slow.
cat <<YAML

  - label: ":art: build frontend ($SHA)"
    key: build-frontend
    agents: { queue: kubernetes }
    plugins:
      - kubernetes:
          podSpec:
            volumes:
              - name: nexus-auth
                secret: { secretName: nexus-push }
            containers:
              - image: quay.io/buildah/stable:v1.40.1
                securityContext:
                  privileged: true
                env:
                  - name: STORAGE_DRIVER
                    value: vfs
                  - name: BUILDAH_FORMAT
                    value: docker
                  - name: REGISTRY_AUTH_FILE
                    value: /auth/config.json
                volumeMounts:
                  - name: nexus-auth
                    mountPath: /auth
                    readOnly: true
                command:
                  - |
                    set -euo pipefail

                    buildah bud \\
                      --tls-verify=false \\
                      --file frontend/Dockerfile \\
                      --tag "$REGISTRY/shop/frontend:$SHA" \\
                      frontend

                    buildah push --tls-verify=false "$REGISTRY/shop/frontend:$SHA"
YAML

# The portal is not a service and does not fit the services template: a
# different Dockerfile path, a different context, and a build measured in
# double-digit minutes.
cat <<YAML

  - label: ":backstage: build portal ($SHA)"
    key: build-portal
    branches: "main"
    agents: { queue: kubernetes }
    timeout_in_minutes: 45
    plugins:
      - kubernetes:
          podSpec:
            volumes:
              - name: nexus-auth
                secret: { secretName: nexus-push }
            containers:
              - image: quay.io/buildah/stable:v1.40.1
                securityContext:
                  privileged: true
                env:
                  - name: STORAGE_DRIVER
                    value: vfs
                  - name: BUILDAH_FORMAT
                    value: docker
                  - name: REGISTRY_AUTH_FILE
                    value: /auth/config.json
                volumeMounts:
                  - name: nexus-auth
                    mountPath: /auth
                    readOnly: true
                command:
                  - |
                    set -euo pipefail
                    buildah bud \\
                      --tls-verify=false \\
                      --file portal/Dockerfile \\
                      --tag "$REGISTRY/shop/portal:$SHA" \\
                      portal

                    buildah push --tls-verify=false "$REGISTRY/shop/portal:$SHA"
YAML

# ── 3. The handoff to CD: write the tag into git ───────────────────────────
cat <<YAML

  - wait

  - label: ":git: bump image tags to $SHA"
    key: deploy
    branches: "main"
    agents: { queue: kubernetes }
    plugins:
      - kubernetes:
          checkout:
            gitCredentialsSecret:
              secretName: git-https-credentials
          podSpec:
            volumes:
              - name: git-creds
                secret: { secretName: git-https-credentials }
            containers:
              - image: alpine/git:2.47.2
                volumeMounts:
                  - name: git-creds
                    mountPath: /gitcreds
                    readOnly: true
                command:
                  - |
                    set -eu
                    git config user.name  "buildkite"
                    git config user.email "buildkite@localtest.me"
                    git config credential.helper "store --file=/gitcreds/.git-credentials"

                    # The overlay has exactly one job - carry the two tags - so
                    # rewriting it wholesale is deterministic and needs no yq.
                    # The tags are literals: pipeline.sh already resolved them.
                    cat > deploy/env/local/values.yaml <<'VALUES'
                    # Generated by Buildkite. Do not edit by hand.
                    orderApi:
                      image:
                        tag: "$SHA"
                    orderWorker:
                      image:
                        tag: "$SHA"
                    # Every service the chart can deploy needs a tag here. One
                    # that is missing falls back to the chart default "dev" —
                    # an image CI never builds — and only that service fails.
                    pricing:
                      v1:
                        image:
                          tag: "$SHA"
                      v2:
                        image:
                          tag: "$SHA"
                    frontend:
                      image:
                        tag: "$SHA"
                    # Every scaffolded service (§14.6) is built from this same
                    # commit, so one tag covers all of them.
                    scaffolded:
                      tag: "$SHA"
                    VALUES

                    git add deploy/env/local/values.yaml
                    if git diff --cached --quiet; then
                      echo "no change; nothing to deploy"
                      exit 0
                    fi

                    git commit -m "chore(deploy): order-platform $SHA [skip ci]"
                    git push origin HEAD:main
                    echo "pushed deploy commit; Argo CD will sync"
YAML
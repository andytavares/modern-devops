---
type: tool
tags: [ci, images, security]
role: daemonless image builds inside CI pods
version: quay.io/buildah/stable:v1.40.1
docs: https://buildah.io/
date_added: 2026-08-17
date_updated: 2026-08-17
status: in-use
---

# Buildah

> [!info] One-liner
> Builds OCI images without a daemon, so a CI pod can build an image without mounting a Docker socket. The interesting part of this page is the capability list, not the tool.

## What it does here

One step per discovered service in `.buildkite/pipeline.sh`:

```sh
buildah bud --tls-verify=false --file services/$SVC/Dockerfile \
  --tag "$REGISTRY/shop/$SVC:$SHA" dist
buildah push --tls-verify=false "$REGISTRY/shop/$SVC:$SHA"
```

**The build context is `dist/`**, not the source tree — [[pants]] already produced the artifact
upstream, so each Dockerfile `COPY`s it by bare name (`order-api.pex`, `pricing.pex`, `order-worker`),
which is what the `output_path` on each Pants target guarantees.

Credentials come from `REGISTRY_AUTH_FILE=/auth/config.json`, mounted from the **Opaque**
`nexus-push` Secret that [[external-secrets-operator]] templates out of [[openbao]] — a plain auth
file, not a `dockerconfigjson`.

`--tls-verify=false` exists **only** because §5.8 runs Nexus on plain HTTP. It disables certificate
verification on a connection carrying push credentials. Behind real TLS you delete the flag and mount
the CA. It is not a Buildah setting you keep.

## Not privileged, and the capability list is the lesson (§12.5)

`privileged: true` is the one-word answer and the wrong one: it grants *every* capability, unconfined
seccomp and AppArmor, and unmasked host devices under `/dev` — so a malicious `Dockerfile` can load a
kernel module or write the host's disk. Almost none of that is what Buildah wanted.

What Buildah documents for running inside an unprivileged container is two settings:

| Setting | What it avoids |
|---|---|
| `BUILDAH_ISOLATION=chroot` | `chroot(2)` instead of a user namespace — no `CLONE_NEWUSER`, no `/etc/subuid` mapping |
| `STORAGE_DRIVER=vfs` | plain directory copies instead of overlayfs — no `mknod` of an overlay device, no nested-mount problem |

With those, the step drops `ALL` and names what is left: SYS_ADMIN, SYS_CHROOT, SETUID, SETGID,
SETPCAP, SETFCAP, CHOWN, DAC_OVERRIDE, FOWNER, FSETID, MKNOD, KILL, NET_RAW, NET_BIND_SERVICE,
AUDIT_WRITE. **That is the default OCI capability set** — not a shopping list. Buildah hands exactly
this set to every `RUN` step inside the build, so it has to hold it in order to grant it. Ask for less
and `RUN apt-get install` fails on `chown`; ask for more and you are privileged by increments.

`seccompProfile: Unconfined` goes with it, because the default profile filters the mount-family
syscalls SYS_ADMIN exists to permit. `allowPrivilegeEscalation: true` stays because setting it false
also sets `no_new_privs`, which stops the setuid helpers Buildah shells out to picking up their
capabilities.

> [!warning] SYS_ADMIN is potent, and this is a hole
> It covers `mount(2)`, which is close enough to arbitrary filesystem control that a determined escape
> is not out of the question. Smaller than privileged — no kernel modules, no `ptrace` outside the
> namespace, no host devices — but a hole. **The production answer is not a shorter capability list; it
> is not building in the workload cluster at all**: a remote BuildKit daemon on dedicated isolated
> nodes, so build pods hold no privilege whatsoever. Kubernetes user namespaces
> (`hostUsers: false`) will eventually make the in-cluster version safe; not yet for this workload.
> **If you take one thing into production from this: builds run on isolated node pools, never
> alongside workloads.**

The [[backstage]] portal build is the exception that proves it — it still runs `privileged: true`, and
takes 20–45 minutes under `vfs`.

[[pants]] shrinks the exposure rather than removing it: the pod used to resolve a dependency tree from
a network index and now copies a file. That is a security argument, not an ergonomics one (§17.1).

> [!warning] Fully qualify every `FROM`
> `docker.io/library/python:3.13-slim`, never `python:3.13-slim`. Docker assumes Docker Hub for a short
> name; Buildah runs `short-name-mode = "enforcing"` and refuses to guess, so an unqualified name that
> works on your laptop stalls or fails in CI. Pinning the registry is the same discipline as pinning
> the tag (§3.2).

> [!warning] Artifact transfer does not preserve file modes
> `pants package` writes an executable `order-worker`, the verify step uploads it as a Buildkite
> artifact, the build step downloads it — and the bit is lost between the two pods. The container then
> fails with `exec: "/order-worker": permission denied` and **no application output at all**. Hence
> `COPY --chmod=0755` in that Dockerfile. The [[pex]] services are immune only because they are invoked
> as `python /app/x.pex` rather than executed directly (§19.5).

## Related

[[buildkite]] · [[pants]] · [[sonatype-nexus]] · [[external-secrets-operator]] · [[immutable-image-tags]] · [[pex]]

---
type: tool
tags: [aws, emulation, testing]
role: Local AWS — S3 and DynamoDB without an AWS account
version: floci/floci:1.5.11
docs: https://github.com/floci-io/floci
date_added: 2026-08-15
date_updated: 2026-08-16
status: in-use
---

# Floci

> [!info] One-liner
> An MIT-licensed AWS emulator serving the real AWS wire protocol on port 4566 — no account, no token, no telemetry.

## What it is

A local AWS service emulator covering ~69 services. Because it speaks the actual AWS protocol,
the AWS SDKs, `aws` CLI, SigV4 signing and pagination all behave normally — your application code
contains **zero** emulator-specific branches. The only difference between local and production is the
value of `AWS_ENDPOINT_URL`, which both `boto3` and `aws-sdk-go-v2` honour natively.

## What it does here

Deployed into the `floci` namespace (§6.2) providing:
- **S3** bucket `orders-raw` — order-api writes raw payloads
- **DynamoDB** table `orders` — order-worker writes rows

Bootstrapped by a Job (§6.3) that carries `sidecar.istio.io/inject: "false"`, because Jobs and
sidecars don't mix. Enrolled in the mesh, behind a default-deny [[istio]] `AuthorizationPolicy` that
allows only `sa/order-api` and `sa/order-worker` (§9.5) — which makes it the best demonstration of
identity-based authz in the platform.

## Why this, not the alternative

**vs LocalStack** — this is a *cost* substitution, not a technical preference, and the tutorial says so
in §0 and §6.1.

**What you get at work is LocalStack Pro.** It is the incumbent AWS emulator by a wide margin, and the
one you should expect to find already installed. We cannot use it here: LocalStack's Community edition
sunset in March 2026 (auth token required for basic usage, last community release frozen with no
security updates); what replaced it is a free **Hobby** tier that is non-commercial-only and still
requires an account, plus paid tiers at **$39–89 per developer per month**
([pricing](https://www.localstack.cloud/pricing), as of 2026-08). A per-seat account gate is
incompatible with a tutorial meant to run offline.

**Why Floci teaches the same thing.** MIT-licensed, no account, no telemetry, ~69 AWS services, and a
drop-in replacement down to serving LocalStack's own `/_localstack/health` endpoint, so existing
tooling and Testcontainers wait strategies keep working. What actually transfers is not Floci: it is
the **AWS wire protocol** — SigV4-signed requests, `boto3` and `aws-sdk-go-v2` behaviour, pagination,
path-style S3 addressing, and the fact that redirecting an SDK at an emulator is one environment
variable (`AWS_ENDPOINT_URL`) rather than a code branch. Swapping Floci for LocalStack Pro changes the
image name and adds an auth token. Nothing else.

**Where it genuinely does not teach the same thing.** Floci is new — repo created February 2026 — so it
has no long track record, and in a real job you will meet LocalStack, not Floci. More importantly,
**IAM policy evaluation is not exercised here at all**: credentials are accepted and never authorised,
so nothing in this platform tells you whether an IAM policy is correct. LocalStack's paid tiers do
emulate IAM enforcement. That is the one capability gap that is a real teaching gap rather than a
licensing one. See also the general emulator caveats under Gotchas.

## Gotchas

- Credentials are ignored but **must be present** — the SDKs refuse to sign without them, hence the
  static `AWS_ACCESS_KEY_ID=test`. In a real cluster those two lines disappear and the pod gets
  credentials from IRSA / Workload Identity. That is the one place "same binary everywhere" leaks.
- `kubectl port-forward svc/floci` **stops working** once STRICT mTLS is on (§6.4). Run the AWS CLI
  in a Pod inside the mesh instead.
- An emulator is not AWS: IAM semantics, consistency and throttling behaviour all differ. Good enough
  to build against, not good enough to certify against.

> [!warning] Needs `enableServiceLinks: false` — hit 2026-08-15
> The `floci` Service shares its namespace with the `floci` pod, so kubelet injects Docker-link-style
> env vars including `FLOCI_PORT=tcp://<clusterIP>:4566`. Floci is a **Quarkus** application, and
> SmallRye Config maps `FLOCI_PORT` to the `floci.port` property (with `quarkus.http.port` derived
> from it) — both of which must be integers:
>
> ```
> SRCFG00029: Expected an integer value, got "tcp://10.96.167.40:4566"
> ```
>
> Environment variables outrank every other SmallRye config source, so the app cannot override it and
> crash-loops. Service links are only injected for Services that **predate** the pod, so this appears
> on a rollout rather than on first deploy — which makes it look like a regression in something else.
>
> The general rule: **any Quarkus/SmallRye service whose Kubernetes Service name matches its config
> prefix will collide this way** (`FOO_PORT` → `foo.port`). Service links are a Docker-links
> compatibility relic; nothing in this platform uses them, so `enableServiceLinks: false` is a safe
> default for any workload here.

## Official docs

- Repo: https://github.com/floci-io/floci
- Site: https://floci.io/

## Open questions

- Which AWS behaviours does Floci *not* emulate faithfully enough to trust (IAM policy evaluation,
  DynamoDB throttling, S3 consistency)?

> [!tip] Related
> [[istio]], [[kubernetes]], [[order-platform]]

---
type: tool
tags: [aws, emulation, testing]
role: Local AWS — S3 and DynamoDB without an AWS account
version: floci/floci:1.5.11
docs: https://github.com/floci-io/floci
date_added: 2026-08-15
date_updated: 2026-08-15
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

**vs LocalStack**: LocalStack's Community edition sunset in March 2026 — basic usage now requires an
auth token and the last community release is frozen with no security updates. Floci is MIT-licensed,
needs no account, and is a drop-in replacement: it even serves LocalStack's `/_localstack/health`
endpoint, so existing tooling and Testcontainers wait strategies keep working.

## Gotchas

- Credentials are ignored but **must be present** — the SDKs refuse to sign without them, hence the
  static `AWS_ACCESS_KEY_ID=test`. In a real cluster those two lines disappear and the pod gets
  credentials from IRSA / Workload Identity. That is the one place "same binary everywhere" leaks.
- `kubectl port-forward svc/floci` **stops working** once STRICT mTLS is on (§6.4). Run the AWS CLI
  in a Pod inside the mesh instead.
- An emulator is not AWS: IAM semantics, consistency and throttling behaviour all differ. Good enough
  to build against, not good enough to certify against.

## Official docs

- Repo: https://github.com/floci-io/floci
- Site: https://floci.io/

## Open questions

- Which AWS behaviours does Floci *not* emulate faithfully enough to trust (IAM policy evaluation,
  DynamoDB throttling, S3 consistency)?

> [!tip] Related
> [[istio]], [[kubernetes]], [[order-platform]]

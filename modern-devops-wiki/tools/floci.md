---
type: tool
tags: [aws, emulator, local-development]
role: S3 and DynamoDB locally, with no AWS account
version: floci/floci:1.5.11
docs: https://github.com/floci-io/floci
date_added: 2026-08-17
date_updated: 2026-08-17
status: in-use
---

# Floci

> [!info] One-liner
> An MIT-licensed AWS emulator serving the real AWS wire protocol on port 4566. Application code contains zero emulator-specific branches — the only difference from production is `AWS_ENDPOINT_URL`.

## What it does here

`deploy/platform/floci.yaml` — one Deployment in the `floci` namespace, `strategy: Recreate` (single
writer; never two with shared storage), plus a Service on 4566. `deploy/platform/floci-bootstrap.yaml`
is a Job creating the `orders-raw` S3 bucket and the `orders` DynamoDB table.

order-api writes the raw payload to S3; order-worker writes the record to DynamoDB. Both reach it via
`http://floci.floci.svc.cluster.local:4566`, injected by the chart's `op.commonEnv` helper.

## Three configuration facts that are not guessable

**`enableServiceLinks: false`.** The `floci` Service is in the same namespace, so the kubelet would
inject `FLOCI_PORT=tcp://<clusterIP>:4566`. Floci is a Quarkus app and SmallRye Config reads that as
the `floci.port` property, which must be an integer — startup then fails on the injected value.

**`FLOCI_HOSTNAME: floci.floci.svc.cluster.local`.** Required when Floci is behind a DNS name other
than localhost, so generated endpoints (S3 virtual-host URLs, SQS queue URLs) point somewhere callers
can reach.

**`FLOCI_STORAGE_MODE: memory`.** State vanishes on restart, which is correct for a disposable dev
environment — every run starts clean and you never debug stale fixtures. It also forces the bootstrap
Job to be re-runnable, which is a property you want anyway. `persistent` (plus a PVC) or `wal` are the
alternatives.

**Credentials are accepted and never validated**, but the SDKs refuse to sign without them, so
`AWS_ACCESS_KEY_ID=test` appears in the chart. `deploy/charts/order-platform/values.yaml` says the rest
out loud: on a real cluster leave both empty, no credential env vars are rendered, and the SDK falls
through to its default provider chain — IRSA or EKS Pod Identity on EKS. **That is the one place
"same binary everywhere" leaks** (§10.1), and it is explicitly *not* a place to reach for the
ExternalSecret pattern, because that still stores a static key.

## The bootstrap Job, and one idiom worth stealing

`|| true` on `create-bucket` makes the Job idempotent; `aws dynamodb wait table-exists` afterwards is
what actually asserts the end state. **Assert the outcome, tolerate the mechanism** (§6.3).

Its pod template carries `sidecar.istio.io/inject: "false"` — harmless before [[istio]] exists,
required after, because a sidecar keeps a Job's pod alive forever (§9.3).

## `port-forward` stops working, and that is correct

§6.4's `kubectl -n floci port-forward svc/floci 4566:4566` dies the moment §9.4 turns on STRICT
[[mtls]] — port-forward delivers plaintext from outside the mesh, which is exactly what STRICT exists
to refuse. You get `Connection reset by peer` from a command that worked yesterday, with nothing in
the logs. The replacement is to run the client *inside* the mesh:

```bash
kubectl -n floci run awscli --rm -it --restart=Never --image=amazon/aws-cli:2.32.9 \
  --env AWS_ENDPOINT_URL=http://floci.floci.svc.cluster.local:4566 \
  --env AWS_DEFAULT_REGION=us-east-1 \
  --env AWS_ACCESS_KEY_ID=test --env AWS_SECRET_ACCESS_KEY=test \
  -- s3 ls s3://orders-raw/ --recursive
```

That pod gets a sidecar and satisfies §9.5's policy — assuming you added its ServiceAccount, which by
default you did not. If it is denied, the policy is working. **Debugging a zero-trust network from
outside it is supposed to be hard; bring your tools inside rather than poking holes.**

## Floci vs LocalStack

[[enterprise-substitution]]. LocalStack Pro is the incumbent by a wide margin and is what you will
meet at work. It cannot be used here: Community sunset in March 2026 (auth token required, last
release frozen with no security updates), replaced by a non-commercial **Hobby** tier that still needs
an account, and paid tiers at **$39–89 per developer per month** (as of 2026-08).

Floci is MIT, no account, no telemetry, ~69 AWS services, and a drop-in replacement down to serving
LocalStack's own `/_localstack/health` endpoint — which is why the probes in `floci.yaml` use it and
Testcontainers wait strategies keep working.

**What transfers is not Floci.** It is the AWS wire protocol: SigV4 signing, `boto3` and
`aws-sdk-go-v2` behaviour, pagination, path-style S3 addressing, and the fact that pointing an SDK at
an emulator is one environment variable rather than a code branch. Swap for LocalStack Pro on Monday
and only the image name and auth token change.

**Where it stops.** The repo dates from February 2026, so there is no long track record. More
importantly, LocalStack Pro emulates **IAM policy evaluation** and Floci does not — credentials are
accepted and never authorised, so *nothing in this tutorial teaches you whether your IAM policy is
correct.* That is the one place the substitution principle leaves a real teaching gap rather than a
licensing one. See [[open-questions]].

## Related

[[enterprise-substitution]] · [[kubernetes]] · [[istio]] · [[mtls]] · [[go]] · [[fastapi]]

---
type: tool
tags: [python, configuration, validation]
role: request validation and environment-driven configuration
version: pydantic 2.11.7, pydantic-settings 2.7.1
docs: https://docs.pydantic.dev/latest/concepts/pydantic_settings/
date_added: 2026-08-17
date_updated: 2026-08-17
status: in-use
---

# pydantic / pydantic-settings

> [!info] One-liner
> Two jobs: validating the request body (`OrderIn`), and parsing the environment into a typed `Settings` object that refuses to start when config is missing. The second is the interesting one.

## Config parsing is validation

`BaseSettings` is the approach FastAPI documents. A field with no default is **required**: the process
refuses to start, and pydantic reports **every** missing or malformed variable at once rather than only
the first. Types are declared, not cast by hand.

> **Why fail at import.** A pod that starts successfully and then 500s on every request is much harder
> to diagnose than one crash-looping with
> `1 validation error for Settings / kafka_brokers / Field required`. Crash-loop is a **good** failure
> mode: `kubectl get pods` shows it, [[argo-cd]] shows it degraded, the alert fires immediately.
> Degrading quietly is the bad one.
>
> A hand-rolled loader can do this too. What it cannot do for free is report *all* the missing
> variables in one message, coerce `PRICING_TIMEOUT_SECONDS` to a float and reject `"soon"`, or stay
> honest about types as the class grows. **You already have a validation library in the image** (§3.1).

## Three details that are not guessable

**`validation_alias` binds a field to a variable name it does not derive.** Matching is
case-insensitive on the **field** name, so `kafka_topic` reads `KAFKA_TOPIC` with nothing declared. Two
fields need more:

- `aws_region` would read `AWS_REGION`; boto3 and every AWS tool own `AWS_DEFAULT_REGION`, so the field
  takes the alias rather than the variable taking our name.
- `signing_key` reads `ORDER_SIGNING_KEY` — the reverse case, where the *variable* is namespaced per
  service (it comes from an [[external-secrets-operator]] Secret in a shared namespace) while the field
  stays generic.

Note that `validation_alias` **replaces** the default name; it does not add an alternative.

**`env_prefix`.** `pricing` uses `env_prefix="PRICING_"` instead, so `PRICING_GRPC_PORT` and
`PRICING_VERSION` are parsed, cast and validated by the library, and a non-numeric port fails at
startup **naming the field**.

> [!warning] `# type: ignore[call-arg]` on `Settings()` is required, not sloppiness
> pydantic's metaclass is a PEP 681 `dataclass_transform`, so [[mypy]] synthesises an `__init__` taking
> every field and reports the required ones as missing arguments. They are not arguments —
> `BaseSettings` reads them from the environment, which is the entire point of the class.

## On the request side

`OrderIn` constrains `customer` (1–128 chars), `sku` (1–64), `quantity` (1–1000) and `amount_cents`
(≥1). Those bounds are what a parametrised test drives to prove invalid orders are rejected before any
side effect runs.

`pricing`'s settings also carry `pricing_timeout_seconds` and `pricing_health_timeout_seconds` on the
caller side — settings rather than constants **because they are the numbers you tune when §9.9 starts
injecting delays**. See [[timeouts-and-retries]].

## Related

[[fastapi]] · [[mypy]] · [[grpc]] · [[external-secrets-operator]] · [[health-checks]] · [[pants]]

---
type: tool
tags: [python, typechecking, build-system]
role: typechecking both Python services, including generated protobuf stubs
version: resolved from locks/python-default.lock via `[mypy] install_from_resolve`
docs: https://mypy.readthedocs.io/
date_added: 2026-08-17
date_updated: 2026-08-17
status: in-use
---

# mypy

> [!info] One-liner
> Runs as part of `pants check ::`. It is on this wiki because two of its failures here are about *generated code and missing type markers*, not about your types.

## Why it needs `.pyi` stubs for protobuf (§18.3)

```toml
[python-protobuf]
generate_type_stubs = true
```

Generated Python protobuf modules do not define message classes the way a reader expects.
`pricing_pb2.py` calls `_builder.BuildTopDescriptorsAndMessages(...)` and the classes appear in
`globals()` **at import time**. mypy reads the file statically, finds no `class PriceOrderRequest`, and
reports `"PriceOrderRequest" is not defined`.

**mypy is correct.** The class genuinely does not exist statically. The setting has protoc emit a
`.pyi` next to each `_pb2.py` describing what will exist at runtime. [[pants]]' own help prefers this
to the older mypy-plugin option.

## Packages with no `py.typed` marker

`grpcio` ships none, so mypy cannot see its types **at all**, regardless of stubs. Verified rather than
assumed: `pants export --resolve=python-default` has no `py.typed` under `grpc/`. The fix is
`types-grpcio` in `3rdparty/python/requirements.txt` — mypy's own suggestion, and it is right.
`types-protobuf` is there for the same reason.

`grpcio-health-checking` also ships none, and it gets a **per-import** ignore rather than a global one:

```python
from grpc_health.v1 import health_pb2, health_pb2_grpc  # type: ignore[import-untyped]
```

A global `ignore_missing_imports` would silence real typos in every other module too.

The same discipline applies to `checks/verify_chart.py`'s one third-party import. `yaml` is installed
in the CI image rather than in the Python resolve, so mypy has nothing to load — that is a **per-module
exception in `mypy.ini` with the reason stated**, not a global switch:

```ini
[mypy-yaml]
ignore_missing_imports = true
```

## The duplicate-module refusal

mypy does not *degrade* on two modules with the same name — it **refuses to run**:
`Duplicate module named "app"`. That is one of the two reasons every service under the shared
`/services/*` source root needs a unique top-level package name. See [[pants]].

## And one ignore that is correct

`settings = Settings()  # type: ignore[call-arg]` — see [[pydantic]].

## Related

[[pants]] · [[grpc]] · [[pydantic]] · [[fastapi]] · [[order-platform]]

"""Config from the environment, validated once at import.

pydantic-settings' `BaseSettings` is the approach FastAPI documents for this
(https://fastapi.tiangolo.com/advanced/settings/, and
https://docs.pydantic.dev/latest/concepts/pydantic_settings/). Environment
variable names match field names case-insensitively, so `service_version` reads
`SERVICE_VERSION`. Where a field must read a variable that is not the upper-cased
field name, pin it with `Field(validation_alias="THE_REAL_NAME")`.

Nothing here is required yet, because a new service has no dependencies. When you
add one, declare the field with no default rather than a default — a field with
no default is required, and the process refuses to start without it. A service
that starts with a silently-wrong config is worse than one that will not start.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    service_version: str = "dev"
    port: int = 8000


settings = Settings()

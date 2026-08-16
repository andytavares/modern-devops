import os


class Settings:
    """Config from environment only. Fail loudly at import if something required is missing.

    Nothing here is required yet, because a new service has no dependencies.
    When you add one, use `_req` rather than a default — a service that starts
    with a silently-wrong config is worse than one that refuses to start.
    """

    def __init__(self) -> None:
        self.service_version = os.getenv("SERVICE_VERSION", "dev")


def _req(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"required environment variable {name} is not set")
    return value


settings = Settings()

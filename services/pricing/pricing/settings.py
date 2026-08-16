import os


class Settings:
    """Config from environment only. Fail loudly at import if something required is missing."""

    def __init__(self) -> None:
        self.grpc_port = int(os.getenv("PRICING_GRPC_PORT", "50051"))
        self.http_port = int(os.getenv("PRICING_HTTP_PORT", "9090"))
        self.version = os.getenv("PRICING_VERSION", "v1")


settings = Settings()

import os


class Settings:
    """Config from environment only. Fail loudly at import if something required is missing."""

    def __init__(self) -> None:
        self.kafka_brokers = _req("KAFKA_BROKERS")
        self.kafka_topic = os.getenv("KAFKA_TOPIC", "orders")
        self.s3_bucket = _req("S3_BUCKET")
        self.aws_endpoint_url = os.getenv("AWS_ENDPOINT_URL") or None
        self.aws_region = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
        # Injected by External Secrets Operator from OpenBao. See §7.
        self.signing_key = _req("ORDER_SIGNING_KEY")
        self.service_version = os.getenv("SERVICE_VERSION", "dev")


def _req(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"required environment variable {name} is not set")
    return value


settings = Settings()
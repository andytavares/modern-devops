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
        self.order_api_port = int(os.getenv("ORDER_API_PORT", "8000"))
        self.pricing_addr = os.getenv(
            "PRICING_ADDR", "pricing.shop.svc.cluster.local:50051"
        )
        self.pricing_timeout_seconds = float(
            os.getenv("PRICING_TIMEOUT_SECONDS", "2.0")
        )


def _req(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"required environment variable {name} is not set")
    return value


settings = Settings()

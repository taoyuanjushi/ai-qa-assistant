import logging


def configure_logging(log_level: str = "INFO") -> None:
    """Configure process-wide logging without exposing secrets."""
    normalized_level = getattr(logging, log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=normalized_level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

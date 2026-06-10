from dataclasses import dataclass
from typing import Any

from app.core.error_codes import ErrorCode


@dataclass(slots=True)
class AppException(Exception):
    """Application-level exception with stable frontend-facing error code."""

    message: str
    code: str = ErrorCode.INTERNAL_ERROR
    status_code: int = 500
    details: dict[str, Any] | list[Any] | None = None

    def __str__(self) -> str:
        return self.message

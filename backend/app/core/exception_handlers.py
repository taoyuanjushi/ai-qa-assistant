import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException


logger = logging.getLogger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    """Register global exception handlers and keep response shape consistent."""

    @app.exception_handler(AppException)
    async def handle_app_exception(
        request: Request,
        exc: AppException,
    ) -> JSONResponse:
        logger.warning(
            "app_exception path=%s code=%s status=%s message=%s",
            request.url.path,
            exc.code,
            exc.status_code,
            exc.message,
        )
        return _error_response(
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
            details=exc.details,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation_error(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        logger.warning(
            "request_validation_error path=%s errors=%s",
            request.url.path,
            exc.errors(),
        )
        return _error_response(
            status_code=422,
            code=ErrorCode.REQUEST_VALIDATION_ERROR,
            message=_format_validation_message(exc),
            details=jsonable_encoder(exc.errors()),
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(
        request: Request,
        exc: StarletteHTTPException,
    ) -> JSONResponse:
        code = ErrorCode.NOT_FOUND if exc.status_code == 404 else ErrorCode.VALIDATION_ERROR
        message = str(exc.detail) if exc.detail else "请求处理失败。"
        logger.warning(
            "http_exception path=%s code=%s status=%s message=%s",
            request.url.path,
            code,
            exc.status_code,
            message,
        )
        return _error_response(
            status_code=exc.status_code,
            code=code,
            message=message,
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_exception(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        logger.exception("unexpected_exception path=%s", request.url.path)
        return _error_response(
            status_code=500,
            code=ErrorCode.INTERNAL_ERROR,
            message="服务内部错误，请稍后重试。",
        )


def _error_response(
    status_code: int,
    code: str,
    message: str,
    details: Any = None,
) -> JSONResponse:
    payload = {
        "error": {
            "code": code,
            "message": message,
            "details": jsonable_encoder(details),
        },
        # Keep old frontend parsing compatible while new clients read error.message.
        "detail": message,
    }
    return JSONResponse(status_code=status_code, content=payload)


def _format_validation_message(exc: RequestValidationError) -> str:
    for error in exc.errors():
        message = str(error.get("msg") or "")
        if "Value error," in message:
            return message.split("Value error,", 1)[1].strip()
        if message:
            return message

    return "请求参数不正确。"

from __future__ import annotations

from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from task_control.domain.errors import TaskControlError


def correlation_id(request: Request) -> str:
    existing = getattr(request.state, "correlation_id", None)
    if existing:
        return existing
    value = request.headers.get("X-Correlation-ID") or str(uuid4())
    request.state.correlation_id = value
    return value


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(TaskControlError)
    async def task_error_handler(request: Request, exc: TaskControlError) -> JSONResponse:
        headers = {}
        if getattr(exc, "retry_after", None):
            headers["Retry-After"] = str(exc.retry_after)
        return JSONResponse(
            status_code=exc.status_code,
            headers=headers,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                    "correlation_id": correlation_id(request),
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {
                "field": ".".join(str(part) for part in error.get("loc", [])[1:]),
                "code": error.get("type", "invalid"),
                "message": error.get("msg", "invalid value"),
            }
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "request validation failed",
                    "details": details,
                    "correlation_id": correlation_id(request),
                }
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "internal server error",
                    "details": [],
                    "correlation_id": correlation_id(request),
                }
            },
        )

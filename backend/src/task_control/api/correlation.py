from __future__ import annotations

import time
from uuid import uuid4

from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        correlation_id = request.headers.get("X-Correlation-ID") or str(uuid4())
        request.state.correlation_id = correlation_id
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.bind(
                correlation_id=correlation_id,
                method=request.method,
                path=request.url.path,
                status=500,
                duration_ms=int((time.perf_counter() - started) * 1000),
            ).exception("request failed")
            raise
        response.headers["X-Correlation-ID"] = correlation_id
        logger.bind(
            correlation_id=correlation_id,
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=int((time.perf_counter() - started) * 1000),
        ).info("request completed")
        return response

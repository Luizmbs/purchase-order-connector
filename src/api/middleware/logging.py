import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

log = structlog.get_logger()


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        query = str(request.url.query)
        log.info(
            "http.request",
            method=request.method,
            path=request.url.path,
            query=query or None,
        )

        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = round((time.perf_counter() - start) * 1000)
            log.exception(
                "http.unhandled_error",
                method=request.method,
                path=request.url.path,
                duration_ms=duration_ms,
            )
            raise

        duration_ms = round((time.perf_counter() - start) * 1000)
        status = response.status_code

        if status >= 500:
            log.error(
                "http.response",
                method=request.method,
                path=request.url.path,
                status_code=status,
                duration_ms=duration_ms,
            )
        elif status >= 400:
            log.warning(
                "http.response",
                method=request.method,
                path=request.url.path,
                status_code=status,
                duration_ms=duration_ms,
            )
        else:
            log.info(
                "http.response",
                method=request.method,
                path=request.url.path,
                status_code=status,
                duration_ms=duration_ms,
            )

        response.headers["X-Request-ID"] = request_id
        return response

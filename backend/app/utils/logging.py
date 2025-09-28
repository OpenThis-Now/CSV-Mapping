from __future__ import annotations

import logging
import sys
import uuid
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


def install_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(handler)


class RequestIDMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, request_id_generator: Optional[callable] = None):
        super().__init__(app)
        import uuid as _uuid
        self.gen = request_id_generator or (lambda: _uuid.uuid4().hex[:8])

    async def dispatch(self, request: Request, call_next):
        request_id = self.gen()
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

"""HTTP middleware: request ids propagated via structlog contextvars."""

from __future__ import annotations

import uuid

import structlog


class RequestIDMiddleware:
    """Accept `X-Request-ID` or mint one; echo it back, bind it to logs."""

    header = "X-Request-ID"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = request.headers.get(self.header) or uuid.uuid4().hex[:16]
        structlog.contextvars.bind_contextvars(request_id=request_id)
        try:
            response = self.get_response(request)
        finally:
            structlog.contextvars.unbind_contextvars("request_id")
        response[self.header] = request_id
        return response

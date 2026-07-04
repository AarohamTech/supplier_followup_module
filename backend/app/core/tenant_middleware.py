"""Raw-ASGI middleware that binds the active company's schema for each request.

Reads the JWT `company` claim from the Authorization header, maps it to a schema
via the company registry cache, and sets the tenant ContextVar for the lifetime
of the request. Raw ASGI (not BaseHTTPMiddleware) so the ContextVar propagates to
the endpoint and its DB session. Fail-open: anything unresolved → default schema.
"""
from __future__ import annotations

from .security import TokenError, decode_token
from .tenant import reset_current_schema, set_current_schema, DEFAULT_SCHEMA
from ..services import company_service


def schema_from_authorization(header: str | None) -> str:
    if not header or not header.lower().startswith("bearer "):
        return DEFAULT_SCHEMA
    token = header.split(" ", 1)[1].strip()
    try:
        payload = decode_token(token)
    except TokenError:
        return DEFAULT_SCHEMA
    return company_service.get_schema_for_code(payload.get("company"))


class TenantMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        header = None
        for key, value in scope.get("headers", []):
            if key == b"authorization":
                header = value.decode("latin-1")
                break
        token = set_current_schema(schema_from_authorization(header))
        try:
            await self.app(scope, receive, send)
        finally:
            reset_current_schema(token)

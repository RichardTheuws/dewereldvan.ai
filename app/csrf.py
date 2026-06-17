"""CSRF protection: a per-session token validated on state-changing requests.

Defense-in-depth on top of the SameSite=Lax session cookie. A high-entropy
token is minted once per session and stored in the signed session cookie.
Every unsafe request (POST/PUT/PATCH/DELETE) must echo it back — either as the
``csrf_token`` form field (plain HTML forms) or the ``X-CSRF-Token`` header
(htmx requests, set globally via ``hx-headers`` on <body>). A missing or
mismatching token is rejected with 403 before the route runs.

Implemented as a pure-ASGI middleware so the request body can be buffered for
inspection and then replayed to the downstream app without breaking the route's
own form parsing (the BaseHTTPMiddleware approach cannot replay the body).
"""

from __future__ import annotations

import hmac
import secrets
from urllib.parse import parse_qs

from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

SESSION_CSRF_KEY = "csrf_token"
FORM_FIELD = "csrf_token"
HEADER_NAME = "x-csrf-token"
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


def get_csrf_token(request: Request) -> str:
    """Return the session CSRF token, minting and storing one on first use."""
    token = request.session.get(SESSION_CSRF_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        request.session[SESSION_CSRF_KEY] = token
    return token


def _token_from_urlencoded(body: bytes) -> str | None:
    values = parse_qs(body.decode("latin-1")).get(FORM_FIELD)
    return values[0] if values else None


class CSRFMiddleware:
    """Ensure a session CSRF token exists and validate it on unsafe methods."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive=receive)
        expected = get_csrf_token(request)  # mints + stores on first use

        if request.method in _SAFE_METHODS:
            await self.app(scope, receive, send)
            return

        submitted = request.headers.get(HEADER_NAME)
        downstream_receive = receive

        if submitted is None:
            content_type = request.headers.get("content-type", "")
            if content_type.startswith("application/x-www-form-urlencoded"):
                body = await request.body()
                submitted = _token_from_urlencoded(body)

                async def downstream_receive() -> Message:
                    return {
                        "type": "http.request",
                        "body": body,
                        "more_body": False,
                    }

        if not submitted or not hmac.compare_digest(submitted, expected):
            response = PlainTextResponse("CSRF-validatie mislukt.", status_code=403)
            await response(scope, receive, send)
            return

        await self.app(scope, downstream_receive, send)

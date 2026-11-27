import asyncio
from time import monotonic

from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from app.services.security import REQUEST_BUDGET, RequestBudget, SecurityDenied, admit_request, digest


class SecurityMiddleware:
    """Bound actual received bytes before parsing; do not trust Content-Length or XFF."""
    def __init__(self, app, max_bytes=32768, timeout=10):
        self.app, self.max_bytes, self.timeout = app, max_bytes, timeout

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope["path"].startswith("/api/"):
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))
        address = (scope.get("client") or ("unknown",))[0]
        # Only the ASGI peer address is trusted. A shared proxy can reduce fairness,
        # but attacker-supplied forwarding headers cannot mint new rate-limit identities.
        token = headers.get(b"x-agent-token", b"")[:100]
        budget = RequestBudget(ip=digest(address), owner=digest(token.decode("latin1")) if token else None)
        reset = REQUEST_BUDGET.set(budget)
        async def private_send(message):
            if message["type"] == "http.response.start":
                message["headers"] = [(key, value) for key, value in message.get("headers", []) if key.lower() != b"cache-control"] + [(b"cache-control", b"no-store, private"), (b"x-content-type-options", b"nosniff")]
            await send(message)
        try:
            if scope.get("method") == "OPTIONS":
                return await self.app(scope, receive, private_send)
            parts, size, deadline = [], 0, monotonic() + self.timeout
            while True:
                remaining = deadline - monotonic()
                if remaining <= 0:
                    raise SecurityDenied("請求接收逾時。", 408)
                try:
                    message = await asyncio.wait_for(receive(), remaining)
                except asyncio.TimeoutError:
                    raise SecurityDenied("請求接收逾時。", 408) from None
                if message["type"] == "http.disconnect":
                    return
                chunk = message.get("body", b"")
                size += len(chunk)
                if size > self.max_bytes:
                    raise SecurityDenied("請求內容過大，請縮短描述。", 413)
                parts.append(chunk)
                if not message.get("more_body", False):
                    break
            await run_in_threadpool(admit_request, scope["path"], scope["method"])
            delivered = False
            async def bounded_receive():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": b"".join(parts), "more_body": False}
                return await receive()
            await self.app(scope, bounded_receive, private_send)
        except SecurityDenied as error:
            await JSONResponse({"detail": error.detail}, status_code=error.status_code, headers=error.headers)(scope, receive, private_send)
        finally:
            REQUEST_BUDGET.reset(reset)

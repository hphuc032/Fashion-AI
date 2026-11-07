"""ASGI boundary checks before route dispatch. Secrets exist only in memory."""
import hashlib
import secrets
import threading
import time
from dataclasses import dataclass

from fashion_api.core.errors import error

COOKIE = "fashion_web_session"


@dataclass
class Session:
    csrf: str
    expires: float


class AccessState:
    def __init__(self, secret: str, bootstrap_ttl=90, session_ttl=3600, clock=time.time):
        if len(secret) < 43:
            raise ValueError("Bootstrap secret must contain at least 256 random bits")
        self.clock, self.session_ttl = clock, session_ttl
        self.digest = hashlib.sha256(secret.encode()).digest()
        self.deadline = clock() + bootstrap_ttl
        self.sessions: dict[str, Session] = {}
        self.lock = threading.Lock()
        self.attempts: list[float] = []

    def exchange(self, supplied):
        with self.lock:
            now = self.clock()
            self.attempts = [v for v in self.attempts if now - v < 60]
            if len(self.attempts) >= 20:
                return None
            self.attempts.append(now)
            if self.digest is None or now >= self.deadline or not secrets.compare_digest(
                    hashlib.sha256(supplied.encode()).digest(), self.digest):
                return None
            self.digest = None
            token = secrets.token_urlsafe(32)
            session = Session(secrets.token_urlsafe(32), now + self.session_ttl)
            self.sessions[hashlib.sha256(token.encode()).hexdigest()] = session
            return token, session

    def lookup(self, token):
        with self.lock:
            now = self.clock()
            self.sessions = {k: v for k, v in self.sessions.items() if now < v.expires}
            return self.sessions.get(hashlib.sha256(token.encode()).hexdigest())

    def revoke(self, token):
        with self.lock:
            self.sessions.pop(hashlib.sha256(token.encode()).hexdigest(), None)

    def clear(self):
        with self.lock:
            self.digest = None
            self.sessions.clear()


class LocalBoundary:
    def __init__(self, app, config, access):
        self.app, self.config, self.access = app, config, access

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = scope["headers"]
        values = lambda name: [v.decode("latin1") for k, v in headers if k.lower() == name]
        hosts = values(b"host")
        origins = values(b"origin")
        origin = origins[0] if len(origins) == 1 else None
        method, path = scope["method"], scope["path"]

        async def secured(message):
            if message["type"] == "http.response.start":
                extra = [(b"cache-control", b"no-store"), (b"x-content-type-options", b"nosniff"),
                         (b"referrer-policy", b"no-referrer"), (b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'")]
                if origin == self.config.frontend_origin:
                    extra += [(b"access-control-allow-origin", origin.encode()),
                              (b"access-control-allow-credentials", b"true"), (b"vary", b"Origin")]
                message = {**message, "headers": [*message.get("headers", []), *extra]}
            await send(message)

        async def reject(status, code, message):
            await error(status, code, message)(scope, receive, secured)

        if hosts != [self.config.backend_host] or any(k.lower() in {
                b"forwarded", b"x-forwarded-host", b"x-forwarded-port", b"x-forwarded-proto"} for k, _ in headers):
            return await reject(400, "HOST_REJECTED", "Invalid local host authority.")
        if len(origins) > 1 or (origins and origin != self.config.frontend_origin):
            return await reject(403, "ORIGIN_REJECTED", "Only the local frontend origin is allowed.")
        if scope.get("query_string"):
            return await reject(400, "QUERY_REJECTED", "Query parameters are not supported in W1.")
        if method == "OPTIONS":
            requested = values(b"access-control-request-method")
            allowed_headers = {"content-type", "x-csrf-token"}
            requested_headers = values(b"access-control-request-headers")
            if origin != self.config.frontend_origin or requested not in (["GET"], ["POST"], ["DELETE"]):
                return await reject(403, "PREFLIGHT_REJECTED", "Invalid preflight.")
            if len(requested_headers) > 1 or (requested_headers and not {
                    h.strip().lower() for h in requested_headers[0].split(",")}.issubset(allowed_headers)):
                return await reject(403, "PREFLIGHT_REJECTED", "Invalid preflight headers.")
            from starlette.responses import Response
            return await Response(status_code=204, headers={"Access-Control-Allow-Methods": "GET, POST, DELETE",
                "Access-Control-Allow-Headers": "Content-Type, X-CSRF-Token", "Access-Control-Max-Age": "300"})(scope, receive, secured)
        public = path == "/api/v1/health" and method == "GET"
        bootstrap = path == "/api/v1/session/bootstrap" and method == "POST"
        mutation = method not in {"GET", "HEAD", "OPTIONS"}
        if (mutation or bootstrap) and origin != self.config.frontend_origin:
            return await reject(403, "ORIGIN_REJECTED", "Mutation requires the local frontend origin.")
        if mutation:
            content = values(b"content-type")
            if method != "DELETE" and (len(content) != 1 or content[0].split(";", 1)[0].lower() != "application/json"):
                return await reject(415, "CONTENT_TYPE_REJECTED", "JSON is required.")
            # W1 accepts only a tiny bootstrap JSON body, never uploads.
            size = 0
            parts = []
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                block = message.get("body", b"")
                size += len(block)
                if size > 2048:
                    return await reject(413, "BODY_TOO_LARGE", "Request body is too large.")
                parts.append(block)
                if not message.get("more_body", False):
                    break
            body = b"".join(parts)
            delivered = False
            original_receive = receive

            async def replay():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": body, "more_body": False}
                return await original_receive()

            receive = replay
        if not public and not bootstrap:
            # Strict cookie parsing avoids ambiguous duplicate session values.
            cookies = values(b"cookie")
            pairs = [v.strip().split("=", 1) for c in cookies for v in c.split(";") if "=" in v]
            tokens = [v for k, v in pairs if k == COOKIE]
            session = self.access.lookup(tokens[0]) if len(tokens) == 1 else None
            if session is None:
                return await reject(401, "SESSION_REQUIRED", "Local session is missing or expired.")
            if mutation:
                csrf = values(b"x-csrf-token")
                if len(csrf) != 1 or not secrets.compare_digest(csrf[0].encode("utf-8"), session.csrf.encode("ascii")):
                    return await reject(403, "CSRF_REJECTED", "Invalid session confirmation.")
            scope.setdefault("state", {}).update(session=session, session_token=tokens[0])
        return await self.app(scope, receive, secured)

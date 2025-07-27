import secrets
from fastapi import Request

CSRF_SESSION_KEY = "csrf_token"

async def get_csrf_token(request: Request) -> str:
    token = request.session.get(CSRF_SESSION_KEY)
    if not token:
        token = secrets.token_hex(16)
        request.session[CSRF_SESSION_KEY] = token
    return token

async def validate_csrf(request: Request, token: str) -> bool:
    session_token = request.session.get(CSRF_SESSION_KEY)
    ok = bool(session_token and token and secrets.compare_digest(session_token, token))
    if ok:
        request.session.pop(CSRF_SESSION_KEY, None)
    return ok

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from typing import Callable, Awaitable

from src.app.utils.session_manager import session_is_valid


class SessionValidationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable]):
        user_id = request.session.get("user_id")
        token = request.session.get("session_token")
        if user_id:
            if not token or not await session_is_valid(int(user_id), token):
                request.session.clear()
        response = await call_next(request)
        return response
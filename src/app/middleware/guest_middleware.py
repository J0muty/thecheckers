from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from typing import Callable, Awaitable

from src.app.utils.guest import generate_guest_id

class GuestMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable]):
        if not request.session.get("user_id"):
            request.session["user_id"] = generate_guest_id()
        response = await call_next(request)
        return response
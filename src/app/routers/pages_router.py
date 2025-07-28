from fastapi import Request, APIRouter
from fastapi.responses import HTMLResponse
from src.settings.settings import templates
from src.app.utils.guest import is_guest

pages_router = APIRouter()


@pages_router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    user_id = request.session.get("user_id")
    flash = request.session.pop("flash", None)
    return templates.TemplateResponse(
        "home.html",
        {
            "request": request,
            "user_id": str(user_id) if user_id else "",
            "is_guest": is_guest(user_id),
            "flash": flash,
        },
    )
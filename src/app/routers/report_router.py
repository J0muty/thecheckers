from fastapi import APIRouter, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from src.settings.settings import templates
from src.base.postgres import get_user_login, get_user_email

report_router = APIRouter()

@report_router.get("/report", response_class=HTMLResponse, name="report")
async def report_page(request: Request):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    uid = int(user_id)
    username = await get_user_login(uid) or str(uid)
    email = await get_user_email(uid) or ""
    return templates.TemplateResponse(
        "report.html", {"request": request, "username": username, "email": email}
    )

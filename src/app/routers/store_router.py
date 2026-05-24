from fastapi import APIRouter, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel

from src.app.utils.guest import is_guest
from src.base.postgres import (
    buy_checker_skin,
    get_checker_store_state,
    get_user_wallet,
    select_checker_skin,
)
from src.settings.settings import templates

store_router = APIRouter()


class SkinAction(BaseModel):
    skin_id: str


def _authenticated_user_id(request: Request) -> int | None:
    user_id = request.session.get("user_id")
    if not user_id or is_guest(user_id):
        return None
    return int(user_id)


@store_router.get("/store", response_class=HTMLResponse, name="store_page")
async def store_page(request: Request):
    user_id = _authenticated_user_id(request)
    if user_id is None:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse("store.html", {"request": request})


@store_router.get("/store/inventory", response_class=HTMLResponse, name="store_inventory_page")
async def store_inventory_page(request: Request):
    user_id = _authenticated_user_id(request)
    if user_id is None:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse(
        "inventory.html",
        {"request": request, "inventory_origin": "store"},
    )


@store_router.get("/api/wallet")
async def api_wallet(request: Request):
    user_id = _authenticated_user_id(request)
    if user_id is None:
        return JSONResponse({"error": "unauthorized"}, status_code=status.HTTP_401_UNAUTHORIZED)
    return JSONResponse(await get_user_wallet(user_id))


@store_router.get("/api/store")
async def api_store(request: Request):
    user_id = _authenticated_user_id(request)
    if user_id is None:
        return JSONResponse({"error": "unauthorized"}, status_code=status.HTTP_401_UNAUTHORIZED)
    return JSONResponse(await get_checker_store_state(user_id))


@store_router.post("/api/store/buy")
async def api_buy_checker_skin(request: Request, action: SkinAction):
    user_id = _authenticated_user_id(request)
    if user_id is None:
        return JSONResponse({"error": "unauthorized"}, status_code=status.HTTP_401_UNAUTHORIZED)
    result = await buy_checker_skin(user_id, action.skin_id)
    status_code = status.HTTP_200_OK if result.get("status") in {"ok", "owned"} else status.HTTP_400_BAD_REQUEST
    return JSONResponse(result, status_code=status_code)


@store_router.post("/api/store/select")
async def api_select_checker_skin(request: Request, action: SkinAction):
    user_id = _authenticated_user_id(request)
    if user_id is None:
        return JSONResponse({"error": "unauthorized"}, status_code=status.HTTP_401_UNAUTHORIZED)
    result = await select_checker_skin(user_id, action.skin_id)
    status_code = status.HTTP_200_OK if result.get("status") == "ok" else status.HTTP_400_BAD_REQUEST
    return JSONResponse(result, status_code=status_code)

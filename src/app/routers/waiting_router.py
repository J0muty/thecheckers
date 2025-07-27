from fastapi import Request, APIRouter, status, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from src.settings.settings import templates
from src.base.redis import (
    add_to_waiting,
    check_waiting,
    cancel_waiting,
    get_board_players,
    get_user_hotseat,
    get_waiting_time,
)
from src.base.lobby_redis import get_user_lobby
from src.base.single_redis import get_user_game
from src.app.routers.single_router import game_colors
from src.app.routers.ws_router import waiting_manager
import json

waiting_router = APIRouter()

@waiting_router.get("/waiting", response_class=HTMLResponse, name="waiting")
async def waiting(request: Request):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    return templates.TemplateResponse(
        "waiting.html",
        {"request": request, "user_id": str(user_id)},
    )


@waiting_router.post("/api/search_game")
async def api_search_game(request: Request):
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401)
    board_id, color = await add_to_waiting(str(user_id))
    if board_id:
        players = await get_board_players(board_id)
        if players:
            for c, uid in players.items():
                await waiting_manager.broadcast(
                    uid,
                    json.dumps({"board_id": board_id, "color": c}),
                )
    return JSONResponse({"board_id": board_id, "color": color})


@waiting_router.get("/api/check_game")
async def api_check_game(request: Request):
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401)
    board_id, color = await check_waiting(str(user_id))
    return JSONResponse({"board_id": board_id, "color": color})

@waiting_router.get("/api/user_status")
async def api_user_status(request: Request):
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401)
    board_id, color = await check_waiting(str(user_id))
    waiting_since = await get_waiting_time(str(user_id))
    single_game = await get_user_game(str(user_id))
    single_color = game_colors.get(single_game, "white") if single_game else None
    hotseat_id = await get_user_hotseat(str(user_id))
    lobby_id = await get_user_lobby(str(user_id))
    return JSONResponse({
        "board_id": board_id,
        "color": color,
        "waiting_since": waiting_since,
        "single_game_id": single_game,
        "single_color": single_color,
        "hotseat_id": hotseat_id,
        "lobby_id": lobby_id,
    })

@waiting_router.post("/api/cancel_game")
async def api_cancel_game(request: Request):
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401)
    await cancel_waiting(str(user_id))
    return JSONResponse({"status": "ok"})
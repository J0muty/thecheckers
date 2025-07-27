import uuid
import json
from fastapi import APIRouter, Request, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from src.settings.settings import templates
from src.base.lobby_redis import (
    create_lobby,
    get_lobby,
    get_user_lobby,
    remove_player,
    set_lobby_board,
    add_player,
    set_lobby_host,
    add_lobby_invite,
    set_invite_status,
    remove_user_invite,
    get_user_invites,
    get_lobby_invites,
    set_player_color,
    get_lobby_colors,
)
from src.base.postgres import get_user_login
from src.base.redis import (
    set_board_players,
    assign_user_board,
    get_lobby_chat_messages,
    save_lobby_chat_message,
)
from src.app.routers.ws_router import waiting_manager, lobby_manager, notify_manager

lobby_router = APIRouter()

async def get_lobby_state(lobby_id: str) -> dict | None:
    lobby = await get_lobby(lobby_id)
    if not lobby:
        return None
    players = []
    player_ids = []
    for uid in lobby.get("players", []):
        login = await get_user_login(int(uid))
        players.append(login or str(uid))
        player_ids.append(uid)
    invites = await get_lobby_invites(lobby_id)
    colors = await get_lobby_colors(lobby_id)
    return {
        "host": lobby.get("host"),
        "players": players,
        "player_ids": player_ids,
        "board_id": lobby.get("board_id"),
        "invites": invites,
        "colors": colors,
    }


async def broadcast_lobby_state(lobby_id: str) -> None:
    state = await get_lobby_state(lobby_id)
    if state is None:
        msg = json.dumps({"type": "closed"})
    else:
        msg = json.dumps({"type": "state", "state": state})
    await lobby_manager.broadcast(lobby_id, msg)

@lobby_router.get("/lobby/new")
async def lobby_new(request: Request):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    existing = await get_user_lobby(str(user_id))
    if existing:
        return RedirectResponse(url=request.url_for("lobby_page", lobby_id=existing))
    lobby_id = await create_lobby(str(user_id))
    return RedirectResponse(url=request.url_for("lobby_page", lobby_id=lobby_id))


@lobby_router.get("/lobby/{lobby_id}", response_class=HTMLResponse, name="lobby_page")
async def lobby_page(request: Request, lobby_id: str):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    lobby = await get_lobby(lobby_id)
    if not lobby or str(user_id) not in lobby.get("players", []):
        return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse(
        "lobby.html",
        {
            "request": request,
            "lobby_id": lobby_id,
            "user_id": str(user_id),
            "host_id": lobby.get("host"),
        },
    )


@lobby_router.get("/api/lobby/{lobby_id}")
async def api_lobby_info(lobby_id: str):
    state = await get_lobby_state(lobby_id)
    if state is None:
        raise HTTPException(status_code=404)
    return JSONResponse(state)

@lobby_router.post("/api/lobby/color/{lobby_id}")
async def api_lobby_color(request: Request, lobby_id: str):
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401)
    lobby = await get_lobby(lobby_id)
    if not lobby or str(user_id) not in lobby.get("players", []):
        raise HTTPException(status_code=403)
    data = await request.json()
    color = data.get("color")
    if color not in ("white", "black", None):
        color = None
    await set_player_color(lobby_id, str(user_id), color)
    await broadcast_lobby_state(lobby_id)
    return JSONResponse({"status": "ok"})


@lobby_router.post("/api/lobby/start/{lobby_id}")
async def api_lobby_start(request: Request, lobby_id: str):
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401)
    lobby = await get_lobby(lobby_id)
    if not lobby or lobby.get("host") != str(user_id):
        raise HTTPException(status_code=403)
    others = [p for p in lobby.get("players", []) if p != str(user_id)]
    if not others:
        raise HTTPException(status_code=400, detail="not enough players")
    colors = lobby.get("colors", {})
    host_color = colors.get(str(user_id))
    other_color = colors.get(others[0])
    if not host_color or not other_color:
        raise HTTPException(status_code=400, detail="color not selected")
    if host_color == other_color:
        raise HTTPException(status_code=400, detail="colors conflict")
    board_id = str(uuid.uuid4())
    players_map = {
        host_color: str(user_id),
        other_color: others[0],
    }
    await set_board_players(board_id, players_map)
    for uid in players_map.values():
        await assign_user_board(uid, board_id)
    await set_lobby_board(lobby_id, board_id)
    await lobby_manager.broadcast(
        lobby_id, json.dumps({"type": "start", "board_id": board_id})
    )
    await broadcast_lobby_state(lobby_id)
    return JSONResponse({"board_id": board_id})


@lobby_router.post("/api/lobby/leave/{lobby_id}")
async def api_lobby_leave(request: Request, lobby_id: str):
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401)
    await remove_player(lobby_id, str(user_id))
    await broadcast_lobby_state(lobby_id)
    return JSONResponse({"status": "ok"})


@lobby_router.post("/api/lobby/kick/{lobby_id}")
async def api_lobby_kick(request: Request, lobby_id: str):
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401)
    lobby = await get_lobby(lobby_id)
    if not lobby or lobby.get("host") != str(user_id):
        raise HTTPException(status_code=403)
    data = await request.json()
    target = str(data.get("id"))
    if target == str(user_id):
        raise HTTPException(status_code=400)
    if target not in lobby.get("players", []):
        raise HTTPException(status_code=404)
    await remove_player(lobby_id, target)
    await broadcast_lobby_state(lobby_id)
    return JSONResponse({"status": "ok"})


@lobby_router.post("/api/lobby/host/{lobby_id}")
async def api_lobby_host(request: Request, lobby_id: str):
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401)
    lobby = await get_lobby(lobby_id)
    if not lobby or lobby.get("host") != str(user_id):
        raise HTTPException(status_code=403)
    data = await request.json()
    to_id = str(data.get("to_id"))
    if to_id not in lobby.get("players", []):
        raise HTTPException(status_code=404)
    await set_lobby_host(lobby_id, to_id)
    await broadcast_lobby_state(lobby_id)
    return JSONResponse({"status": "ok"})


@lobby_router.post("/api/lobby/invite/{lobby_id}")
async def api_lobby_invite(request: Request, lobby_id: str, to_id: int):
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401)
    lobby = await get_lobby(lobby_id)
    if not lobby or lobby.get("host") != str(user_id):
        raise HTTPException(status_code=403)
    if len(lobby.get("players", [])) >= 2:
        raise HTTPException(status_code=400, detail="lobby full")
    await add_lobby_invite(lobby_id, str(to_id), str(user_id))
    msg = json.dumps({"type": "invite", "lobby_id": lobby_id, "from": str(user_id)})
    await notify_manager.broadcast(str(to_id), msg)
    await broadcast_lobby_state(lobby_id)
    return JSONResponse({"status": "ok"})


@lobby_router.post("/api/lobby/respond/{lobby_id}")
async def api_lobby_respond(request: Request, lobby_id: str, action: str):
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401)
    lobby = await get_lobby(lobby_id)
    if not lobby:
        raise HTTPException(status_code=404)
    if action == "accept":
        if len(lobby.get("players", [])) >= 2:
            raise HTTPException(status_code=400, detail="lobby full")
        await add_player(lobby_id, str(user_id))
        await set_invite_status(lobby_id, str(user_id), None)
        await remove_user_invite(str(user_id), lobby_id)
        await broadcast_lobby_state(lobby_id)
        await notify_manager.broadcast(
            lobby.get("host"),
            json.dumps({"type": "invite_accept", "user_id": str(user_id), "lobby_id": lobby_id}),
        )
    elif action == "decline":
        await set_invite_status(lobby_id, str(user_id), "declined")
        await remove_user_invite(str(user_id), lobby_id)
        await broadcast_lobby_state(lobby_id)
        await notify_manager.broadcast(lobby.get("host"), json.dumps({"type": "invite_decline", "user_id": str(user_id), "lobby_id": lobby_id}))
    return JSONResponse({"status": "ok"})


@lobby_router.get("/api/lobby/messages/{lobby_id}")
async def api_lobby_messages(lobby_id: str):
    msgs = await get_lobby_chat_messages(lobby_id)
    enriched = []
    for m in msgs:
        login = await get_user_login(int(m.get("sender")))
        m["login"] = login or str(m.get("sender"))
        enriched.append(m)
    return JSONResponse({"messages": enriched})

@lobby_router.get("/api/invites")
async def api_get_invites(request: Request):
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401)
    invites = await get_user_invites(str(user_id))
    result = []
    for lid, frm in invites.items():
        login = await get_user_login(int(frm))
        result.append({"lobby_id": lid, "from_id": frm, "from_login": login or str(frm)})
    return JSONResponse({"invites": result})

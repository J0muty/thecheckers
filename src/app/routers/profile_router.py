import json
from fastapi import Request, APIRouter, status, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from src.settings.settings import templates
from src.base.postgres import (
    get_user_stats, get_user_login, get_friends, get_friend_requests,
    search_users, send_friend_request, cancel_friend_request,
    remove_friend, get_user_history, get_2fa_info,
    set_2fa_secret, enable_2fa, disable_2fa
)
from src.app.routers.ws_router import friends_manager
from src.app.utils.session_manager import (
    get_sessions, delete_session, delete_all_sessions
)
from src.app.utils.totp import generate_secret, build_uri, verify_code

profile_router = APIRouter()

@profile_router.get("/profile", response_class=HTMLResponse, name="profile")
async def profile(request: Request):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    username = await get_user_login(int(user_id))
    return templates.TemplateResponse(
        "profile.html", {"request": request, "username": username or str(user_id)}
    )

@profile_router.get("/profile/friends", response_class=HTMLResponse, name="friends")
async def friends(request: Request):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse(
        "friends.html", {"request": request, "user_id": str(user_id)}
    )

@profile_router.get("/profile/achievements", response_class=HTMLResponse, name="achievements")
async def achievements(request: Request):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse("achievements.html", {"request": request})

@profile_router.get("/api/friends")
async def api_friends(request: Request):
    user_id = request.session.get("user_id")
    if not user_id:
        return JSONResponse({"error": "unauthorized"}, status_code=status.HTTP_401_UNAUTHORIZED)
    uid = int(user_id)
    friends = await get_friends(uid)
    requests = await get_friend_requests(uid)
    return JSONResponse({"friends": friends, "requests": requests})

@profile_router.get("/api/search_users")
async def api_search_users(request: Request, q: str):
    user_id = request.session.get("user_id")
    if not user_id:
        return JSONResponse({"error": "unauthorized"}, status_code=status.HTTP_401_UNAUTHORIZED)
    uid = int(user_id)
    users = await search_users(q, uid)
    return JSONResponse({"users": users})

@profile_router.post("/api/friend_request")
async def api_friend_request(request: Request, to_id: int, action: str = "send"):
    user_id = request.session.get("user_id")
    if not user_id:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    uid = int(user_id)
    if action == "send":
        await send_friend_request(uid, to_id)
    elif action == "cancel":
        await cancel_friend_request(uid, to_id)
    elif action == "accept":
        await send_friend_request(uid, to_id)
    elif action == "reject":
        await cancel_friend_request(to_id, uid)
    elif action == "remove":
        await remove_friend(uid, to_id)
    else:
        return JSONResponse({"error": "unknown action"}, status_code=400)
    msg = json.dumps({"action": "update"})
    await friends_manager.broadcast(str(uid), msg)
    await friends_manager.broadcast(str(to_id), msg)
    return JSONResponse({"status": "ok"})

@profile_router.get("/api/sessions")
async def api_sessions(request: Request):
    user_id = request.session.get("user_id")
    if not user_id:
        return JSONResponse({"error": "unauthorized"}, status_code=status.HTTP_401_UNAUTHORIZED)
    sessions = await get_sessions(int(user_id))
    return JSONResponse({"sessions": sessions})

@profile_router.post("/api/sessions/logout")
async def api_logout_session(request: Request, token: str = Form(...)):
    user_id = request.session.get("user_id")
    if not user_id:
        return JSONResponse({"error": "unauthorized"}, status_code=status.HTTP_401_UNAUTHORIZED)
    await delete_session(int(user_id), token)
    logged_out = False
    if token == request.session.get("session_token"):
        request.session.clear()
        logged_out = True
    return JSONResponse({"status": "ok", "logged_out": logged_out})

@profile_router.post("/api/sessions/logout_all")
async def api_logout_all(request: Request):
    user_id = request.session.get("user_id")
    if not user_id:
        return JSONResponse({"error": "unauthorized"}, status_code=status.HTTP_401_UNAUTHORIZED)
    await delete_all_sessions(int(user_id))
    request.session.clear()
    return JSONResponse({"status": "ok", "logged_out": True})

@profile_router.get("/profile/settings", response_class=HTMLResponse, name="settings")
async def settings(request: Request):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    info = await get_2fa_info(int(user_id))
    return templates.TemplateResponse("settings.html", {"request": request, "twofa_enabled": info["enabled"]})

@profile_router.get("/api/stats")
async def api_stats(request: Request):
    user_id = request.session.get("user_id")
    if not user_id:
        return JSONResponse({"error": "unauthorized"}, status_code=status.HTTP_401_UNAUTHORIZED)
    uid = int(user_id)
    stats = await get_user_stats(uid)
    return JSONResponse(stats)

@profile_router.get("/api/history")
async def api_history(request: Request, offset: int = 0, limit: int = 10):
    user_id = request.session.get("user_id")
    if not user_id:
        return JSONResponse({"error": "unauthorized"}, status_code=status.HTTP_401_UNAUTHORIZED)
    uid = int(user_id)
    history = await get_user_history(uid, offset=offset, limit=limit)
    return JSONResponse({"history": history})

@profile_router.post("/api/2fa/setup/start")
async def api_2fa_start(request: Request):
    user_id = request.session.get("user_id")
    if not user_id:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    uid = int(user_id)
    secret = generate_secret()
    await set_2fa_secret(uid, secret)
    username = await get_user_login(uid) or str(uid)
    uri = build_uri(secret, username, "TheCheckers")
    return JSONResponse({"secret": secret, "uri": uri})

@profile_router.post("/api/2fa/enable")
async def api_2fa_enable(request: Request, code: str = Form(...)):
    user_id = request.session.get("user_id")
    if not user_id:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    info = await get_2fa_info(int(user_id))
    if not info["secret"]:
        return JSONResponse({"error": "no_secret"}, status_code=400)
    if not verify_code(info["secret"], code):
        return JSONResponse({"error": "invalid_code"}, status_code=400)
    await enable_2fa(int(user_id))
    return JSONResponse({"status": "ok"})

@profile_router.post("/api/2fa/disable")
async def api_2fa_disable(request: Request, code: str = Form(...)):
    user_id = request.session.get("user_id")
    if not user_id:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    info = await get_2fa_info(int(user_id))
    if not info["enabled"]:
        return JSONResponse({"error": "not_enabled"}, status_code=400)
    if not verify_code(info["secret"], code):
        return JSONResponse({"error": "invalid_code"}, status_code=400)
    await disable_2fa(int(user_id))
    return JSONResponse({"status": "ok"})

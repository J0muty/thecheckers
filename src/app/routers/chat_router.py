from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from src.base.redis import get_user_chats, get_chat_messages, save_chat_message
from src.base.postgres import get_user_login
from src.app.routers.ws_router import chat_manager
import json

chat_router = APIRouter()

@chat_router.get("/api/chats")
async def api_chats(request: Request):
    user_id = request.session.get("user_id")
    if not user_id:
        return JSONResponse({"error": "unauthorized"}, status_code=status.HTTP_401_UNAUTHORIZED)
    chat_ids = await get_user_chats(int(user_id))
    chats = []
    for cid in chat_ids:
        a, b = map(int, cid.split(":"))
        other = b if a == int(user_id) else a
        login = await get_user_login(other)
        chats.append({"id": cid, "title": login or str(other)})
    return JSONResponse({"chats": chats})


@chat_router.get("/api/messages/{other_id}")
async def api_messages(request: Request, other_id: int):
    user_id = request.session.get("user_id")
    if not user_id:
        return JSONResponse({"error": "unauthorized"}, status_code=status.HTTP_401_UNAUTHORIZED)
    cid, msgs = await get_chat_messages(int(user_id), other_id)
    for m in msgs:
        login = await get_user_login(int(m.get("sender")))
        m["login"] = login or str(m.get("sender"))
    return JSONResponse({"chat_id": cid, "messages": msgs})


@chat_router.post("/api/messages")
async def api_send_message(request: Request, to_id: int, text: str):
    user_id = request.session.get("user_id")
    if not user_id:
        return JSONResponse({"error": "unauthorized"}, status_code=status.HTTP_401_UNAUTHORIZED)
    cid, _ = await save_chat_message(int(user_id), to_id, text)
    await chat_manager.broadcast(cid, json.dumps({"sender": int(user_id), "text": text}))
    return JSONResponse({"status": "ok"})
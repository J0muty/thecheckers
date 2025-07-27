from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Dict, List
import json

from src.base.redis import save_chat_message, save_lobby_chat_message
from src.base.postgres import get_user_login

ws_router = APIRouter()


class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, key: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.setdefault(key, []).append(websocket)

    def disconnect(self, key: str, websocket: WebSocket) -> None:
        conns = self.active_connections.get(key)
        if conns:
            if websocket in conns:
                conns.remove(websocket)
            if not conns:
                del self.active_connections[key]

    async def broadcast(self, key: str, message: str) -> None:
        for ws in list(self.active_connections.get(key, [])):
            try:
                await ws.send_text(message)
            except Exception:
                self.disconnect(key, ws)


board_manager = ConnectionManager()
single_board_manager = ConnectionManager()
waiting_manager = ConnectionManager()
friends_manager = ConnectionManager()
chat_manager = ConnectionManager()
lobby_manager = ConnectionManager()
notify_manager = ConnectionManager()
lobby_chat_manager = ConnectionManager()
session_update_manager = ConnectionManager()
session_kick_manager = ConnectionManager()


@ws_router.websocket("/ws/single/{game_id}")
async def websocket_single_board(websocket: WebSocket, game_id: str):
    await single_board_manager.connect(game_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        single_board_manager.disconnect(game_id, websocket)


@ws_router.websocket("/ws/board/{board_id}")
async def websocket_board(websocket: WebSocket, board_id: str):
    await board_manager.connect(board_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        board_manager.disconnect(board_id, websocket)


@ws_router.websocket("/ws/waiting/{user_id}")
async def websocket_waiting(websocket: WebSocket, user_id: str):
    await waiting_manager.connect(user_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        waiting_manager.disconnect(user_id, websocket)


@ws_router.websocket("/ws/friends/{user_id}")
async def websocket_friends(websocket: WebSocket, user_id: str):
    await friends_manager.connect(user_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        friends_manager.disconnect(user_id, websocket)


@ws_router.websocket("/ws/chat/{chat_id}")
async def websocket_chat(websocket: WebSocket, chat_id: str):
    await chat_manager.connect(chat_id, websocket)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                payload = json.loads(data)
                sender = int(payload.get("sender"))
                receiver = int(payload.get("receiver"))
                text = payload.get("text", "")
            except Exception:
                continue
            await save_chat_message(sender, receiver, text)
            login = await get_user_login(sender)
            msg = json.dumps(
                {"sender": sender, "text": text, "login": login or str(sender)}
            )
            await chat_manager.broadcast(chat_id, msg)
    except WebSocketDisconnect:
        chat_manager.disconnect(chat_id, websocket)


@ws_router.websocket("/ws/lobby/{lobby_id}")
async def websocket_lobby(websocket: WebSocket, lobby_id: str):
    await lobby_manager.connect(lobby_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        lobby_manager.disconnect(lobby_id, websocket)


@ws_router.websocket("/ws/lobby_chat/{lobby_id}")
async def websocket_lobby_chat(websocket: WebSocket, lobby_id: str):
    await lobby_chat_manager.connect(lobby_id, websocket)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                payload = json.loads(data)
                sender = int(payload.get("sender"))
                text = payload.get("text", "")
            except Exception:
                continue
            await save_lobby_chat_message(lobby_id, sender, text)
            login = await get_user_login(sender)
            msg = json.dumps(
                {"sender": sender, "text": text, "login": login or str(sender)}
            )
            await lobby_chat_manager.broadcast(lobby_id, msg)
    except WebSocketDisconnect:
        lobby_chat_manager.disconnect(lobby_id, websocket)


@ws_router.websocket("/ws/notifications/{user_id}")
async def websocket_notifications(websocket: WebSocket, user_id: str):
    await notify_manager.connect(user_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        notify_manager.disconnect(user_id, websocket)


@ws_router.websocket("/ws/sessions/{user_id}")
async def websocket_sessions(websocket: WebSocket, user_id: str):
    await session_update_manager.connect(user_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        session_update_manager.disconnect(user_id, websocket)


@ws_router.websocket("/ws/session/{token}")
async def websocket_session(websocket: WebSocket, token: str):
    await session_kick_manager.connect(token, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        session_kick_manager.disconnect(token, websocket)

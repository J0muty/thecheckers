from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Any, Dict, List
import json

from src.app.game.game_logic import piece_capture_moves
from src.base.postgres import get_user_login
from src.base.redis import (
    board_exists as multi_board_exists,
    get_board_players,
    get_board_state as get_multi_board_state,
    get_chain_state as get_multi_chain_state,
    get_current_timers as get_multi_timers,
    get_history as get_multi_history,
    save_chat_message,
    save_lobby_chat_message,
)
from src.base.hotseat_redis import (
    game_exists as hotseat_exists,
    get_board_state as get_hotseat_board_state,
    get_chain_state as get_hotseat_chain_state,
    get_current_timers as get_hotseat_timers,
    get_history as get_hotseat_history,
)
from src.base.single_redis import (
    game_exists as single_exists,
    get_board_state as get_single_board_state,
    get_chain_state as get_single_chain_state,
    get_current_timers as get_single_timers,
    get_history as get_single_history,
)
from src.app.utils.guest import get_display_name

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


def _public_timers(timers: dict[str, Any] | None) -> dict[str, Any] | None:
    if not timers:
        return None
    return {key: value for key, value in timers.items() if key != "last_ts"}


def _blocked_positions(chain_state: dict | None) -> list[tuple[int, int]]:
    if not chain_state:
        return []
    return [tuple(pos) for pos in chain_state.get("captured_positions", [])]


def _forced_piece(chain_state: dict | None) -> tuple[int, int] | None:
    if not chain_state or "piece" not in chain_state:
        return None
    piece = chain_state.get("piece")
    return tuple(piece) if piece else None


def _forced_payload(board, chain_state: dict | None):
    forced_piece = _forced_piece(chain_state)
    if forced_piece is None or not chain_state:
        return None, []
    moves = piece_capture_moves(
        board,
        forced_piece,
        chain_state["player"],
        blocked_positions=_blocked_positions(chain_state),
    )
    return forced_piece, moves


async def _send_initial_single_state(websocket: WebSocket, game_id: str) -> None:
    if not await single_exists(game_id):
        return
    board = await get_single_board_state(game_id, create=False)
    timers = await get_single_timers(game_id, create=False)
    if board is None or timers is None:
        return
    history = await get_single_history(game_id)
    forced_piece, forced_moves = _forced_payload(
        board,
        await get_single_chain_state(game_id),
    )
    await websocket.send_text(json.dumps({
        "board": board,
        "status": None,
        "history": history,
        "timers": _public_timers(timers),
        "forced_piece": forced_piece,
        "forced_moves": forced_moves,
    }))


async def _send_initial_board_state(websocket: WebSocket, board_id: str) -> None:
    if await multi_board_exists(board_id):
        board = await get_multi_board_state(board_id, create=False)
        timers = await get_multi_timers(board_id, create=False)
        if board is None or timers is None:
            return
        history = await get_multi_history(board_id)
        players_raw = await get_board_players(board_id) or {}
        players = {
            color: await get_display_name(uid)
            for color, uid in players_raw.items()
        }
        forced_piece, forced_moves = _forced_payload(
            board,
            await get_multi_chain_state(board_id),
        )
        await websocket.send_text(json.dumps({
            "board": board,
            "status": None,
            "history": history,
            "timers": _public_timers(timers),
            "players": players,
            "forced_piece": forced_piece,
            "forced_moves": forced_moves,
        }))
        return

    if await hotseat_exists(board_id):
        board = await get_hotseat_board_state(board_id, create=False)
        timers = await get_hotseat_timers(board_id, create=False)
        if board is None or timers is None:
            return
        history = await get_hotseat_history(board_id)
        forced_piece, forced_moves = _forced_payload(
            board,
            await get_hotseat_chain_state(board_id),
        )
        await websocket.send_text(json.dumps({
            "board": board,
            "status": None,
            "history": history,
            "timers": _public_timers(timers),
            "forced_piece": forced_piece,
            "forced_moves": forced_moves,
        }))


@ws_router.websocket("/ws/single/{game_id}")
async def websocket_single_board(websocket: WebSocket, game_id: str):
    await single_board_manager.connect(game_id, websocket)
    await _send_initial_single_state(websocket, game_id)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        single_board_manager.disconnect(game_id, websocket)


@ws_router.websocket("/ws/board/{board_id}")
async def websocket_board(websocket: WebSocket, board_id: str):
    await board_manager.connect(board_id, websocket)
    await _send_initial_board_state(websocket, board_id)
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

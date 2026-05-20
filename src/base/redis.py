import json
import logging
import time
import uuid
from typing import Any, List, Tuple

import redis.asyncio as redis

from src.app.game.game_logic import Board, create_initial_board, rebuild_board_from_history
from src.app.game.draw_logic import initial_draw_state
from src.settings.config import redis_host, redis_port, redis_db
from src.app.utils.guest import is_guest

redis_client = redis.Redis(
    host=redis_host, port=redis_port, db=redis_db, decode_responses=True
)

REDIS_KEY_PREFIX = "board"
USER_BOARD_KEY_PREFIX = "user_board"
USER_HOTSEAT_KEY_PREFIX = "user_hotseat"
HISTORY_KEY_PREFIX = "history"
TIMER_KEY_PREFIX = "timer"
PLAYERS_KEY = "players"
CHAIN_KEY_PREFIX = "chain"
DRAW_OFFER_KEY_PREFIX = "draw_offer"
DRAW_STATE_KEY_PREFIX = "draw_state"
DEFAULT_TIME = 600
WAITING_KEY_REG = "waiting_user_reg"
WAITING_KEY_GUEST = "waiting_user_guest"
WAITING_TIME_PREFIX_REG = "waiting_time_reg"
WAITING_TIME_PREFIX_GUEST = "waiting_time_guest"
WAITING_TIMEOUT = 600
CHAT_PREFIX = "chats"
LOBBY_CHAT_PREFIX = "lobby_chat"
REMATCH_INVITES_PREFIX = "rematch_invites"
USER_REMATCH_PREFIX = "user_rematch"

logger = logging.getLogger(__name__)


def _board_key(board_id: str) -> str:
    return f"{REDIS_KEY_PREFIX}:{board_id}:state"


def _history_key(board_id: str) -> str:
    return f"{REDIS_KEY_PREFIX}:{board_id}:{HISTORY_KEY_PREFIX}"


def _timer_key(board_id: str) -> str:
    return f"{REDIS_KEY_PREFIX}:{board_id}:{TIMER_KEY_PREFIX}"


def _players_key(board_id: str) -> str:
    return f"{REDIS_KEY_PREFIX}:{board_id}:{PLAYERS_KEY}"


def _chain_key(board_id: str) -> str:
    return f"{REDIS_KEY_PREFIX}:{board_id}:{CHAIN_KEY_PREFIX}"


def _draw_key(board_id: str) -> str:
    return f"{REDIS_KEY_PREFIX}:{board_id}:{DRAW_STATE_KEY_PREFIX}"


def _waiting_key(username: str) -> str:
    return WAITING_KEY_GUEST if is_guest(username) else WAITING_KEY_REG

def _waiting_time_prefix(username: str) -> str:
    return (
        WAITING_TIME_PREFIX_GUEST if is_guest(username) else WAITING_TIME_PREFIX_REG
    )

async def check_redis_connection():
    print("Проверка подключения к редису...")
    try:
        pong = await redis_client.ping()
        if pong:
            print("✅ Успешное подключение к Redis!")
        else:
            print("❌ Пинг не прошёл. Redis недоступен.")
    except Exception as e:
        print(f"❌ Ошибка подключения к Redis: {e}")

async def board_exists(board_id: str) -> bool:
    return bool(await redis_client.exists(_board_key(board_id)))

async def get_board_state(board_id: str, create: bool = True):
    key = _board_key(board_id)
    raw = await redis_client.get(key)
    if not raw:
        if not create:
            return None
        board = create_initial_board()
        pipe = redis_client.pipeline(transaction=True)
        pipe.set(key, json.dumps(board))
        pipe.set(_draw_key(board_id), json.dumps(initial_draw_state(board)))
        await pipe.execute()
        return board
    return json.loads(raw)

async def save_board_state(board_id: str, board):
    await redis_client.set(_board_key(board_id), json.dumps(board))

async def assign_user_board(username: str, board_id: str):
    key = f"{USER_BOARD_KEY_PREFIX}:{username}"
    await redis_client.set(key, board_id)

async def assign_user_hotseat(username: str, board_id: str):
    key = f"{USER_HOTSEAT_KEY_PREFIX}:{username}"
    await redis_client.set(key, board_id)

async def set_board_players(board_id: str, players: dict):
    await redis_client.set(_players_key(board_id), json.dumps(players))

async def get_board_players(board_id: str):
    raw = await redis_client.get(_players_key(board_id))
    return json.loads(raw) if raw else None

async def get_user_board(username: str):
    key = f"{USER_BOARD_KEY_PREFIX}:{username}"
    return await redis_client.get(key)

async def get_user_hotseat(username: str):
    key = f"{USER_HOTSEAT_KEY_PREFIX}:{username}"
    return await redis_client.get(key)

async def clear_user_hotseat(username: str):
    key = f"{USER_HOTSEAT_KEY_PREFIX}:{username}"
    await redis_client.delete(key)

async def get_history(board_id: str):
    raw = await redis_client.lrange(_history_key(board_id), 0, -1)
    return raw if raw is not None else []

async def append_history(board_id: str, move: str):
    await redis_client.rpush(_history_key(board_id), move)

async def _read_timers(board_id: str, create: bool = True):
    """Read timers for a board.

    When ``create`` is ``False`` the function returns ``None`` if no timers are
    stored, instead of initialising them. This helps to avoid resurrecting
    expired games when a client polls old endpoints.
    """
    key = _timer_key(board_id)
    raw = await redis_client.get(key)
    if not raw:
        if not create:
            return None
        timers = {
            "white": DEFAULT_TIME,
            "black": DEFAULT_TIME,
            "turn": "white",
            "last_ts": time.time(),
        }
        await redis_client.set(key, json.dumps(timers))
        return timers
    return json.loads(raw)

async def get_current_timers(board_id: str, create: bool = True):
    timers = await _read_timers(board_id, create=create)
    if timers is None:
        return None
    turn = timers.get("turn")
    if turn in ("white", "black"):
        now = time.time()
        elapsed = now - timers["last_ts"]
        timers_view = timers.copy()
        timers_view[turn] = max(0, timers_view[turn] - elapsed)
        return timers_view
    return timers

async def apply_move_timer(board_id: str, player: str):
    timers = await _read_timers(board_id)
    now = time.time()
    elapsed = now - timers["last_ts"]
    timers[player] = max(0, timers[player] - elapsed)
    timers["turn"] = "black" if player == "white" else "white"
    timers["last_ts"] = now
    await redis_client.set(_timer_key(board_id), json.dumps(timers))
    return timers

async def apply_same_turn_timer(board_id: str, player: str):
    timers = await _read_timers(board_id)
    now = time.time()
    elapsed = now - timers["last_ts"]
    timers[player] = max(0, timers[player] - elapsed)
    timers["last_ts"] = now
    await redis_client.set(_timer_key(board_id), json.dumps(timers))
    return timers

async def freeze_timers(board_id: str):
    timers = await _read_timers(board_id, create=False)
    if timers is None:
        return None
    turn = timers.get("turn")
    if turn in ("white", "black"):
        now = time.time()
        elapsed = now - timers["last_ts"]
        timers[turn] = max(0, timers[turn] - elapsed)
        timers["last_ts"] = now
    timers["turn"] = "stopped"
    await redis_client.set(_timer_key(board_id), json.dumps(timers))
    return timers


async def get_chain_state(board_id: str) -> dict[str, Any] | None:
    raw = await redis_client.get(_chain_key(board_id))
    return json.loads(raw) if raw else None


async def save_chain_state(board_id: str, state: dict[str, Any] | None) -> None:
    key = _chain_key(board_id)
    if state is None:
        await redis_client.delete(key)
        return
    await redis_client.set(key, json.dumps(state))


async def clear_chain_state(board_id: str) -> None:
    await redis_client.delete(_chain_key(board_id))


async def get_draw_state(board_id: str) -> dict[str, Any] | None:
    raw = await redis_client.get(_draw_key(board_id))
    return json.loads(raw) if raw else None


async def save_draw_state(board_id: str, state: dict[str, Any] | None) -> None:
    key = _draw_key(board_id)
    if state is None:
        await redis_client.delete(key)
        return
    await redis_client.set(key, json.dumps(state))


async def clear_draw_state(board_id: str) -> None:
    await redis_client.delete(_draw_key(board_id))


async def get_board_state_at(board_id: str, index: int) -> Board:
    history = await get_history(board_id)
    logger.info("Rebuilding board %s at step %d", board_id, index)
    if index >= len(history):
        logger.info("Requested index %d beyond history length %d", index, len(history))
        return await get_board_state(board_id)
    return rebuild_board_from_history(history, index=index)

async def add_to_waiting(username: str):
    board_id = await get_user_board(username)
    if board_id:
        players = await get_board_players(board_id)
        if players:
            color = "white" if players.get("white") == username else "black"
            return board_id, color
    wkey = _waiting_key(username)
    waiting = await redis_client.get(wkey)
    if waiting and await waiting_timed_out(waiting):
        waiting = None
    if waiting and waiting != username:
        board_id = str(uuid.uuid4())
        await redis_client.delete(wkey)
        await redis_client.delete(f"{_waiting_time_prefix(waiting)}:{waiting}")
        await assign_user_board(waiting, board_id)
        await assign_user_board(username, board_id)
        await set_board_players(board_id, {"white": waiting, "black": username})
        return board_id, "black"
    if waiting == username:
        return None, None
    await redis_client.set(wkey, username, ex=WAITING_TIMEOUT)
    await redis_client.set(
        f"{_waiting_time_prefix(username)}:{username}", time.time(), ex=WAITING_TIMEOUT
    )
    return None, None

async def check_waiting(username: str):
    board_id = await get_user_board(username)
    if board_id:
        players = await get_board_players(board_id)
        if players:
            color = "white" if players.get("white") == username else "black"
            return board_id, color
        else:
            await redis_client.delete(f"{USER_BOARD_KEY_PREFIX}:{username}")
    if await waiting_timed_out(username):
        return None, None
    return None, None

async def get_waiting_time(username: str):
    key = f"{_waiting_time_prefix(username)}:{username}"
    ts = await redis_client.get(key)
    return float(ts) if ts else None

async def waiting_timed_out(username: str) -> bool:
    ts = await get_waiting_time(username)
    if ts and time.time() - ts >= WAITING_TIMEOUT:
        await cancel_waiting(username)
        return True
    return False

async def cancel_waiting(username: str):
    wkey = _waiting_key(username)
    waiting = await redis_client.get(wkey)
    if waiting == username:
        await redis_client.delete(wkey)
        await redis_client.delete(f"{_waiting_time_prefix(username)}:{username}")
    await redis_client.delete(f"{USER_BOARD_KEY_PREFIX}:{username}")

async def cleanup_board(board_id: str):
    players = await get_board_players(board_id) or {}
    for user in players.values():
        await redis_client.delete(f"{USER_BOARD_KEY_PREFIX}:{user}")
        await redis_client.delete(f"{USER_HOTSEAT_KEY_PREFIX}:{user}")
    keys = await redis_client.keys(f"{REDIS_KEY_PREFIX}:{board_id}:*")
    if keys:
        await redis_client.delete(*keys)

async def expire_board(board_id: str, delay: int = 300):
    players = await get_board_players(board_id) or {}
    for user in players.values():
        await redis_client.delete(f"{USER_BOARD_KEY_PREFIX}:{user}")
        await redis_client.delete(f"{USER_HOTSEAT_KEY_PREFIX}:{user}")
    keys = await redis_client.keys(f"{REDIS_KEY_PREFIX}:{board_id}:*")
    for key in keys:
        await redis_client.expire(key, delay)

async def set_draw_offer(board_id: str, player: str):
    key = f"{REDIS_KEY_PREFIX}:{board_id}:{DRAW_OFFER_KEY_PREFIX}"
    await redis_client.set(key, player)

async def get_draw_offer(board_id: str):
    key = f"{REDIS_KEY_PREFIX}:{board_id}:{DRAW_OFFER_KEY_PREFIX}"
    return await redis_client.get(key)

async def clear_draw_offer(board_id: str):
    key = f"{REDIS_KEY_PREFIX}:{board_id}:{DRAW_OFFER_KEY_PREFIX}"
    await redis_client.delete(key)

def _chat_id(user1: int, user2: int) -> str:
    a, b = sorted([int(user1), int(user2)])
    return f"{a}:{b}"

async def save_chat_message(sender_id: int, receiver_id: int, text: str):
    cid = _chat_id(sender_id, receiver_id)
    msg = {"sender": sender_id, "text": text, "ts": time.time()}
    await redis_client.rpush(f"{CHAT_PREFIX}:{cid}", json.dumps(msg))
    return cid, msg

async def get_chat_messages(user1: int, user2: int, limit: int = 50):
    cid = _chat_id(user1, user2)
    raw = await redis_client.lrange(f"{CHAT_PREFIX}:{cid}", -limit, -1)
    msgs = [json.loads(m) for m in raw]
    return cid, msgs

async def get_user_chats(user_id: int) -> List[str]:
    pattern = f"{CHAT_PREFIX}:*"
    keys = await redis_client.keys(pattern)
    uid = str(int(user_id))
    cids = []
    for key in keys:
        cid = key[len(CHAT_PREFIX) + 1:]
        if uid in cid.split(":"):
            cids.append(cid)
    return cids

async def save_lobby_chat_message(lobby_id: str, sender: int, text: str):
    msg = {"sender": sender, "text": text, "ts": time.time()}
    await redis_client.rpush(f"{LOBBY_CHAT_PREFIX}:{lobby_id}", json.dumps(msg))
    return msg

async def get_lobby_chat_messages(lobby_id: str, limit: int = 50):
    raw = await redis_client.lrange(f"{LOBBY_CHAT_PREFIX}:{lobby_id}", -limit, -1)
    return [json.loads(m) for m in raw]

async def clear_lobby_chat(lobby_id: str):
    await redis_client.delete(f"{LOBBY_CHAT_PREFIX}:{lobby_id}")

async def _read_rematch_invites(board_id: str) -> dict:
    raw = await redis_client.get(f"{REMATCH_INVITES_PREFIX}:{board_id}")
    return json.loads(raw) if raw else {}

async def _write_rematch_invites(board_id: str, data: dict) -> None:
    await redis_client.set(f"{REMATCH_INVITES_PREFIX}:{board_id}", json.dumps(data))

async def _read_user_rematch(user_id: str) -> dict:
    raw = await redis_client.get(f"{USER_REMATCH_PREFIX}:{user_id}")
    return json.loads(raw) if raw else {}

async def _write_user_rematch(user_id: str, data: dict) -> None:
    await redis_client.set(f"{USER_REMATCH_PREFIX}:{user_id}", json.dumps(data))

async def add_rematch_invite(board_id: str, to_id: str, from_id: str) -> None:
    board_invites = await _read_rematch_invites(board_id)
    board_invites[to_id] = from_id
    await _write_rematch_invites(board_id, board_invites)
    user_invites = await _read_user_rematch(to_id)
    user_invites[board_id] = from_id
    await _write_user_rematch(to_id, user_invites)

async def remove_rematch_invite(board_id: str, user_id: str) -> None:
    board_invites = await _read_rematch_invites(board_id)
    board_invites.pop(user_id, None)
    await _write_rematch_invites(board_id, board_invites)
    user_invites = await _read_user_rematch(user_id)
    user_invites.pop(board_id, None)
    await _write_user_rematch(user_id, user_invites)

async def get_user_rematch_invites(user_id: str) -> dict:
    return await _read_user_rematch(user_id)

async def get_board_rematch_invites(board_id: str) -> dict:
    return await _read_rematch_invites(board_id)

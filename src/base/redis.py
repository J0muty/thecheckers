import json
import redis.asyncio as redis
import time
import logging
import uuid
from typing import List, Tuple
from src.app.game.game_logic import create_initial_board, validate_move, Board
from src.settings.config import redis_host, redis_port, redis_db

redis_client = redis.Redis(
    host=redis_host, port=redis_port, db=redis_db, decode_responses=True
)

REDIS_KEY_PREFIX = "board"
USER_BOARD_KEY_PREFIX = "user_board"
USER_HOTSEAT_KEY_PREFIX = "user_hotseat"
HISTORY_KEY_PREFIX = "history"
TIMER_KEY_PREFIX = "timer"
PLAYERS_KEY = "players"
DRAW_OFFER_KEY_PREFIX = "draw_offer"
DEFAULT_TIME = 600
WAITING_KEY = "waiting_user"
WAITING_TIME_PREFIX = "waiting_time"
WAITING_TIMEOUT = 600
CHAT_PREFIX = "chats"
LOBBY_CHAT_PREFIX = "lobby_chat"
REMATCH_INVITES_PREFIX = "rematch_invites"
USER_REMATCH_PREFIX = "user_rematch"

logger = logging.getLogger(__name__)


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
    """Return ``True`` if any state is stored for the given board."""
    key = f"{REDIS_KEY_PREFIX}:{board_id}:state"
    return bool(await redis_client.exists(key))


async def get_board_state(board_id: str, create: bool = True):
    """Return board state or ``None`` if it does not exist.

    When ``create`` is ``True`` a missing board will be initialised and stored
    in Redis. This behaviour is useful when a new game is being created.  For
    read-only operations use ``create=False`` to avoid accidental board
    creation when the game no longer exists.
    """
    key = f"{REDIS_KEY_PREFIX}:{board_id}:state"
    raw = await redis_client.get(key)
    if not raw:
        if not create:
            return None
        board = await create_initial_board()
        await redis_client.set(key, json.dumps(board))
        return board
    return json.loads(raw)


async def save_board_state(board_id: str, board):
    key = f"{REDIS_KEY_PREFIX}:{board_id}:state"
    await redis_client.set(key, json.dumps(board))


async def assign_user_board(username: str, board_id: str):
    key = f"{USER_BOARD_KEY_PREFIX}:{username}"
    await redis_client.set(key, board_id)


async def assign_user_hotseat(username: str, board_id: str):
    key = f"{USER_HOTSEAT_KEY_PREFIX}:{username}"
    await redis_client.set(key, board_id)


async def set_board_players(board_id: str, players: dict):
    key = f"{REDIS_KEY_PREFIX}:{board_id}:{PLAYERS_KEY}"
    await redis_client.set(key, json.dumps(players))


async def get_board_players(board_id: str):
    key = f"{REDIS_KEY_PREFIX}:{board_id}:{PLAYERS_KEY}"
    raw = await redis_client.get(key)
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
    key = f"{REDIS_KEY_PREFIX}:{board_id}:{HISTORY_KEY_PREFIX}"
    raw = await redis_client.get(key)
    if not raw:
        return []
    return json.loads(raw)


async def append_history(board_id: str, move: str):
    history = await get_history(board_id)
    history.append(move)
    key = f"{REDIS_KEY_PREFIX}:{board_id}:{HISTORY_KEY_PREFIX}"
    await redis_client.set(key, json.dumps(history))


async def _read_timers(board_id: str, create: bool = True):
    """Read timers for a board.

    When ``create`` is ``False`` the function returns ``None`` if no timers are
    stored, instead of initialising them. This helps to avoid resurrecting
    expired games when a client polls old endpoints.
    """
    key = f"{REDIS_KEY_PREFIX}:{board_id}:{TIMER_KEY_PREFIX}"
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
    key = f"{REDIS_KEY_PREFIX}:{board_id}:{TIMER_KEY_PREFIX}"
    await redis_client.set(key, json.dumps(timers))
    return timers


async def apply_same_turn_timer(board_id: str, player: str):
    timers = await _read_timers(board_id)
    now = time.time()
    elapsed = now - timers["last_ts"]
    timers[player] = max(0, timers[player] - elapsed)
    timers["last_ts"] = now
    key = f"{REDIS_KEY_PREFIX}:{board_id}:{TIMER_KEY_PREFIX}"
    await redis_client.set(key, json.dumps(timers))
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
    key = f"{REDIS_KEY_PREFIX}:{board_id}:{TIMER_KEY_PREFIX}"
    await redis_client.set(key, json.dumps(timers))
    return timers

async def get_board_state_at(board_id: str, index: int) -> Board:
    history = await get_history(board_id)
    logger.info("Rebuilding board %s at step %d", board_id, index)
    if index >= len(history):
        logger.info("Requested index %d beyond history length %d", index, len(history))
        return await get_board_state(board_id)

    parsed_moves: List[Tuple[Tuple[int, int], Tuple[int, int]]] = []
    for mv in history[:index]:
        start_str, end_str = mv.split("->")
        start = (8 - int(start_str[1]), ord(start_str[0]) - 65)
        end = (8 - int(end_str[1]), ord(end_str[0]) - 65)
        parsed_moves.append((start, end))

    board = await create_initial_board()
    player = "white"

    for i, (start, end) in enumerate(parsed_moves):
        logger.debug("Replaying step %d by %s: %s -> %s", i + 1, player, start, end)
        board = await validate_move(board, start, end, player)

        dr = abs(end[0] - start[0])
        dc = abs(end[1] - start[1])
        is_capture = dr > 1 or dc > 1

        next_in_chain = (
            is_capture and i + 1 < len(parsed_moves) and parsed_moves[i + 1][0] == end
        )

        if not next_in_chain:
            player = "black" if player == "white" else "white"

    return board


async def add_to_waiting(username: str):
    board_id = await get_user_board(username)
    if board_id:
        players = await get_board_players(board_id)
        if players:
            color = "white" if players.get("white") == username else "black"
            return board_id, color
    waiting = await redis_client.get(WAITING_KEY)
    if waiting and await waiting_timed_out(waiting):
        waiting = None
    if waiting and waiting != username:
        board_id = str(uuid.uuid4())
        await redis_client.delete(WAITING_KEY)
        await redis_client.delete(f"{WAITING_TIME_PREFIX}:{waiting}")
        await assign_user_board(waiting, board_id)
        await assign_user_board(username, board_id)
        await set_board_players(board_id, {"white": waiting, "black": username})
        return board_id, "black"
    if waiting == username:
        return None, None
    await redis_client.set(WAITING_KEY, username, ex=WAITING_TIMEOUT)
    await redis_client.set(
        f"{WAITING_TIME_PREFIX}:{username}", time.time(), ex=WAITING_TIMEOUT
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
    key = f"{WAITING_TIME_PREFIX}:{username}"
    ts = await redis_client.get(key)
    return float(ts) if ts else None


async def waiting_timed_out(username: str) -> bool:
    ts = await get_waiting_time(username)
    if ts and time.time() - ts >= WAITING_TIMEOUT:
        await cancel_waiting(username)
        return True
    return False


async def cancel_waiting(username: str):
    waiting = await redis_client.get(WAITING_KEY)
    if waiting == username:
        await redis_client.delete(WAITING_KEY)
        await redis_client.delete(f"{WAITING_TIME_PREFIX}:{username}")
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
        cid = key[len(CHAT_PREFIX) + 1 :]
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
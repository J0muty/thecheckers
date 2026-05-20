import json
import logging
import time
from typing import Any, List

from .redis import redis_client
from src.app.game.game_logic import Board, create_initial_board, rebuild_board_from_history
from src.app.game.draw_logic import initial_draw_state

SINGLE_REDIS_KEY_PREFIX = "single_board"
HISTORY_KEY_PREFIX = "history"
TIMER_KEY_PREFIX = "timer"
CHAIN_KEY_PREFIX = "chain"
DRAW_STATE_KEY_PREFIX = "draw_state"
USER_GAME_KEY_PREFIX = "single_user_game"
GAME_USER_KEY_PREFIX = "single_game_user"
DEFAULT_TIME = 600

logger = logging.getLogger(__name__)


def _state_key(game_id: str) -> str:
    return f"{SINGLE_REDIS_KEY_PREFIX}:{game_id}:state"


def _history_key(game_id: str) -> str:
    return f"{SINGLE_REDIS_KEY_PREFIX}:{game_id}:{HISTORY_KEY_PREFIX}"


def _timer_key(game_id: str) -> str:
    return f"{SINGLE_REDIS_KEY_PREFIX}:{game_id}:{TIMER_KEY_PREFIX}"


def _chain_key(game_id: str) -> str:
    return f"{SINGLE_REDIS_KEY_PREFIX}:{game_id}:{CHAIN_KEY_PREFIX}"


def _draw_key(game_id: str) -> str:
    return f"{SINGLE_REDIS_KEY_PREFIX}:{game_id}:{DRAW_STATE_KEY_PREFIX}"


async def _matching_keys(pattern: str) -> list[str]:
    return [key async for key in redis_client.scan_iter(match=pattern)]


async def _history_type(key: str) -> str:
    return await redis_client.type(key)


async def _read_history_string(key: str) -> list[str]:
    raw = await redis_client.get(key)
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return value if isinstance(value, list) else []


async def _migrate_history_to_list(key: str, history: list[str]) -> None:
    pipe = redis_client.pipeline(transaction=True)
    pipe.delete(key)
    if history:
        pipe.rpush(key, *history)
    await pipe.execute()


async def game_exists(game_id: str) -> bool:
    return bool(await redis_client.exists(_state_key(game_id)))


async def get_board_state(game_id: str, create: bool = True) -> Board | None:
    raw = await redis_client.get(_state_key(game_id))
    if not raw:
        if not create:
            return None
        board = create_initial_board()
        pipe = redis_client.pipeline(transaction=True)
        pipe.set(_state_key(game_id), json.dumps(board))
        pipe.set(_draw_key(game_id), json.dumps(initial_draw_state(board)))
        await pipe.execute()
        return board
    return json.loads(raw)


async def save_board_state(game_id: str, board: Board) -> None:
    await redis_client.set(_state_key(game_id), json.dumps(board))


async def get_history(game_id: str) -> List[str]:
    key = _history_key(game_id)
    key_type = await _history_type(key)
    if key_type == "none":
        return []
    if key_type == "list":
        return await redis_client.lrange(key, 0, -1)
    history = await _read_history_string(key)
    if history:
        await _migrate_history_to_list(key, history)
    return history


async def append_history(game_id: str, move: str) -> None:
    key = _history_key(game_id)
    key_type = await _history_type(key)
    if key_type == "string":
        history = await _read_history_string(key)
        history.append(move)
        await _migrate_history_to_list(key, history)
        return
    await redis_client.rpush(key, move)


async def _read_timers(game_id: str, create: bool = True) -> dict[str, Any] | None:
    raw = await redis_client.get(_timer_key(game_id))
    if not raw:
        if not create:
            return None
        timers = {
            "white": DEFAULT_TIME,
            "black": DEFAULT_TIME,
            "turn": "white",
            "last_ts": time.time(),
        }
        await redis_client.set(_timer_key(game_id), json.dumps(timers))
        return timers
    return json.loads(raw)


async def get_current_timers(game_id: str, create: bool = True):
    timers = await _read_timers(game_id, create=create)
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


async def apply_move_timer(game_id: str, player: str):
    timers = await _read_timers(game_id)
    now = time.time()
    elapsed = now - timers["last_ts"]
    timers[player] = max(0, timers[player] - elapsed)
    timers["turn"] = "black" if player == "white" else "white"
    timers["last_ts"] = now
    await redis_client.set(_timer_key(game_id), json.dumps(timers))
    return timers


async def apply_same_turn_timer(game_id: str, player: str):
    timers = await _read_timers(game_id)
    now = time.time()
    elapsed = now - timers["last_ts"]
    timers[player] = max(0, timers[player] - elapsed)
    timers["last_ts"] = now
    await redis_client.set(_timer_key(game_id), json.dumps(timers))
    return timers


async def freeze_timers(game_id: str):
    timers = await _read_timers(game_id, create=False)
    if timers is None:
        return None
    turn = timers.get("turn")
    if turn in ("white", "black"):
        now = time.time()
        elapsed = now - timers["last_ts"]
        timers[turn] = max(0, timers[turn] - elapsed)
        timers["last_ts"] = now
    timers["turn"] = "stopped"
    await redis_client.set(_timer_key(game_id), json.dumps(timers))
    return timers


async def get_chain_state(game_id: str) -> dict[str, Any] | None:
    raw = await redis_client.get(_chain_key(game_id))
    return json.loads(raw) if raw else None


async def save_chain_state(game_id: str, state: dict[str, Any] | None) -> None:
    key = _chain_key(game_id)
    if state is None:
        await redis_client.delete(key)
        return
    await redis_client.set(key, json.dumps(state))


async def clear_chain_state(game_id: str) -> None:
    await redis_client.delete(_chain_key(game_id))


async def get_draw_state(game_id: str) -> dict[str, Any] | None:
    raw = await redis_client.get(_draw_key(game_id))
    return json.loads(raw) if raw else None


async def save_draw_state(game_id: str, state: dict[str, Any] | None) -> None:
    key = _draw_key(game_id)
    if state is None:
        await redis_client.delete(key)
        return
    await redis_client.set(key, json.dumps(state))


async def clear_draw_state(game_id: str) -> None:
    await redis_client.delete(_draw_key(game_id))


async def get_board_state_at(game_id: str, index: int) -> Board:
    history = await get_history(game_id)
    logger.info("Rebuilding single board %s at step %d", game_id, index)
    if index >= len(history):
        return await get_board_state(game_id)
    return rebuild_board_from_history(history, index=index)


async def cleanup_board(game_id: str):
    keys = await _matching_keys(f"{SINGLE_REDIS_KEY_PREFIX}:{game_id}:*")
    if keys:
        await redis_client.delete(*keys)
    user = await redis_client.get(f"{GAME_USER_KEY_PREFIX}:{game_id}")
    if user:
        await redis_client.delete(f"{GAME_USER_KEY_PREFIX}:{game_id}")
        await redis_client.delete(f"{USER_GAME_KEY_PREFIX}:{user}")


async def expire_board(game_id: str, delay: int = 300):
    keys = await _matching_keys(f"{SINGLE_REDIS_KEY_PREFIX}:{game_id}:*")
    for key in keys:
        await redis_client.expire(key, delay)
    user = await redis_client.get(f"{GAME_USER_KEY_PREFIX}:{game_id}")
    if user:
        await redis_client.delete(f"{GAME_USER_KEY_PREFIX}:{game_id}")
        await redis_client.delete(f"{USER_GAME_KEY_PREFIX}:{user}")


async def assign_user_game(user_id: str, game_id: str):
    await redis_client.set(f"{USER_GAME_KEY_PREFIX}:{user_id}", game_id)
    await redis_client.set(f"{GAME_USER_KEY_PREFIX}:{game_id}", user_id)


async def get_user_game(user_id: str):
    return await redis_client.get(f"{USER_GAME_KEY_PREFIX}:{user_id}")


async def get_game_user(game_id: str):
    return await redis_client.get(f"{GAME_USER_KEY_PREFIX}:{game_id}")

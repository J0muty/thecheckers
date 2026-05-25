import json
import logging
import time
from typing import Any, List

from .redis import redis_client
from src.app.game.game_logic import Board, create_initial_board, rebuild_board_from_history
from src.app.game.draw_logic import initial_draw_state
from src.app.utils.guest import is_guest
from src.base import redis_keys as keys
from src.base.redis_names import user_folder, user_id_from_folder

HISTORY_KEY_PREFIX = "history"
TIMER_KEY_PREFIX = "timer"
CHAIN_KEY_PREFIX = "chain"
DRAW_STATE_KEY_PREFIX = "draw_state"
DEFAULT_TIME = 600

logger = logging.getLogger(__name__)


async def _matching_keys(pattern: str) -> list[str]:
    return [key async for key in redis_client.scan_iter(match=pattern)]


async def _owner(game_id: str) -> str:
    return await redis_client.get(keys.hotseat_owner_key(game_id)) or keys.ORPHAN_USER


async def _field_key(game_id: str, field: str) -> str:
    return keys.hotseat_game_key(await _owner(game_id), game_id, field)


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
    return bool(await redis_client.exists(await _field_key(game_id, "state")))


async def get_board_state(game_id: str, create: bool = True) -> Board | None:
    state_key = await _field_key(game_id, "state")
    raw = await redis_client.get(state_key)
    if not raw:
        if not create:
            return None
        board = create_initial_board()
        pipe = redis_client.pipeline(transaction=True)
        pipe.set(state_key, json.dumps(board))
        pipe.set(await _field_key(game_id, DRAW_STATE_KEY_PREFIX), json.dumps(initial_draw_state(board)))
        await pipe.execute()
        return board
    return json.loads(raw)


async def save_board_state(game_id: str, board: Board) -> None:
    await redis_client.set(await _field_key(game_id, "state"), json.dumps(board))


async def get_history(game_id: str) -> List[str]:
    key = await _field_key(game_id, HISTORY_KEY_PREFIX)
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
    key = await _field_key(game_id, HISTORY_KEY_PREFIX)
    key_type = await _history_type(key)
    if key_type == "string":
        history = await _read_history_string(key)
        history.append(move)
        await _migrate_history_to_list(key, history)
        return
    await redis_client.rpush(key, move)


async def _read_timers(game_id: str, create: bool = True) -> dict[str, Any] | None:
    key = await _field_key(game_id, TIMER_KEY_PREFIX)
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
    await redis_client.set(await _field_key(game_id, TIMER_KEY_PREFIX), json.dumps(timers))
    return timers


async def apply_same_turn_timer(game_id: str, player: str):
    timers = await _read_timers(game_id)
    now = time.time()
    elapsed = now - timers["last_ts"]
    timers[player] = max(0, timers[player] - elapsed)
    timers["last_ts"] = now
    await redis_client.set(await _field_key(game_id, TIMER_KEY_PREFIX), json.dumps(timers))
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
    await redis_client.set(await _field_key(game_id, TIMER_KEY_PREFIX), json.dumps(timers))
    return timers


async def get_chain_state(game_id: str) -> dict[str, Any] | None:
    raw = await redis_client.get(await _field_key(game_id, CHAIN_KEY_PREFIX))
    return json.loads(raw) if raw else None


async def save_chain_state(game_id: str, state: dict[str, Any] | None) -> None:
    key = await _field_key(game_id, CHAIN_KEY_PREFIX)
    if state is None:
        await redis_client.delete(key)
        return
    await redis_client.set(key, json.dumps(state))


async def clear_chain_state(game_id: str) -> None:
    await redis_client.delete(await _field_key(game_id, CHAIN_KEY_PREFIX))


async def get_draw_state(game_id: str) -> dict[str, Any] | None:
    raw = await redis_client.get(await _field_key(game_id, DRAW_STATE_KEY_PREFIX))
    return json.loads(raw) if raw else None


async def save_draw_state(game_id: str, state: dict[str, Any] | None) -> None:
    key = await _field_key(game_id, DRAW_STATE_KEY_PREFIX)
    if state is None:
        await redis_client.delete(key)
        return
    await redis_client.set(key, json.dumps(state))


async def clear_draw_state(game_id: str) -> None:
    await redis_client.delete(await _field_key(game_id, DRAW_STATE_KEY_PREFIX))


async def get_board_state_at(game_id: str, index: int) -> Board:
    history = await get_history(game_id)
    logger.info("Rebuilding hotseat board %s at step %d", game_id, index)
    if index >= len(history):
        return await get_board_state(game_id)
    return rebuild_board_from_history(history, index=index)


async def cleanup_board(game_id: str):
    owner = await _owner(game_id)
    keys_to_delete = await _matching_keys(keys.hotseat_game_pattern(owner, game_id))
    user = await get_game_user(game_id)
    if user:
        keys_to_delete.append(keys.hotseat_active_key(await user_folder(user)))
    keys_to_delete.append(keys.hotseat_owner_key(game_id))
    if keys_to_delete:
        await redis_client.delete(*keys_to_delete)


async def expire_board(game_id: str, delay: int = 300):
    owner = await _owner(game_id)
    user = await get_game_user(game_id)
    actual_delay = max(delay, keys.GUEST_FINISHED_GAME_TTL_SECONDS) if user and is_guest(str(user)) else delay
    for key in await _matching_keys(keys.hotseat_game_pattern(owner, game_id)):
        await redis_client.expire(key, actual_delay)
    await redis_client.expire(keys.hotseat_owner_key(game_id), actual_delay)
    if user:
        await redis_client.delete(keys.hotseat_active_key(await user_folder(user)))


async def get_game_user(game_id: str) -> str | None:
    owner = await redis_client.get(keys.hotseat_owner_key(game_id))
    if owner and owner != keys.ORPHAN_USER:
        return await user_id_from_folder(owner)
    for key in await _matching_keys("users:*:games:multiplayer:hotseat:active"):
        val = await redis_client.get(key)
        if val == game_id:
            return await user_id_from_folder(key.split(":", 2)[1])
    return None

import json
import time
import logging
from typing import List, Tuple

from .redis import redis_client, USER_HOTSEAT_KEY_PREFIX
from src.app.game.game_logic import create_initial_board, validate_move, Board

HOTSEAT_REDIS_KEY_PREFIX = "hotseat_board"
HISTORY_KEY_PREFIX = "history"
TIMER_KEY_PREFIX = "timer"
DEFAULT_TIME = 600

logger = logging.getLogger(__name__)


async def game_exists(game_id: str) -> bool:
    """Check if a hotseat game state exists."""
    key = f"{HOTSEAT_REDIS_KEY_PREFIX}:{game_id}:state"
    return bool(await redis_client.exists(key))


async def get_board_state(game_id: str, create: bool = True) -> Board | None:
    key = f"{HOTSEAT_REDIS_KEY_PREFIX}:{game_id}:state"
    raw = await redis_client.get(key)
    if not raw:
        if not create:
            return None
        board = await create_initial_board()
        await redis_client.set(key, json.dumps(board))
        return board
    return json.loads(raw)


async def save_board_state(game_id: str, board: Board) -> None:
    key = f"{HOTSEAT_REDIS_KEY_PREFIX}:{game_id}:state"
    await redis_client.set(key, json.dumps(board))


async def get_history(game_id: str) -> List[str]:
    key = f"{HOTSEAT_REDIS_KEY_PREFIX}:{game_id}:{HISTORY_KEY_PREFIX}"
    raw = await redis_client.get(key)
    if not raw:
        return []
    return json.loads(raw)


async def append_history(game_id: str, move: str) -> None:
    history = await get_history(game_id)
    history.append(move)
    key = f"{HOTSEAT_REDIS_KEY_PREFIX}:{game_id}:{HISTORY_KEY_PREFIX}"
    await redis_client.set(key, json.dumps(history))


async def _read_timers(game_id: str, create: bool = True):
    key = f"{HOTSEAT_REDIS_KEY_PREFIX}:{game_id}:{TIMER_KEY_PREFIX}"
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
    key = f"{HOTSEAT_REDIS_KEY_PREFIX}:{game_id}:{TIMER_KEY_PREFIX}"
    await redis_client.set(key, json.dumps(timers))
    return timers


async def apply_same_turn_timer(game_id: str, player: str):
    timers = await _read_timers(game_id)
    now = time.time()
    elapsed = now - timers["last_ts"]
    timers[player] = max(0, timers[player] - elapsed)
    timers["last_ts"] = now
    key = f"{HOTSEAT_REDIS_KEY_PREFIX}:{game_id}:{TIMER_KEY_PREFIX}"
    await redis_client.set(key, json.dumps(timers))
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
    key = f"{HOTSEAT_REDIS_KEY_PREFIX}:{game_id}:{TIMER_KEY_PREFIX}"
    await redis_client.set(key, json.dumps(timers))
    return timers

async def get_board_state_at(game_id: str, index: int) -> Board:
    history = await get_history(game_id)
    logger.info("Rebuilding hotseat board %s at step %d", game_id, index)
    if index >= len(history):
        return await get_board_state(game_id)

    parsed_moves: List[Tuple[Tuple[int, int], Tuple[int, int]]] = []
    for mv in history[:index]:
        start_str, end_str = mv.split("->")
        start = (8 - int(start_str[1]), ord(start_str[0]) - 65)
        end = (8 - int(end_str[1]), ord(end_str[0]) - 65)
        parsed_moves.append((start, end))

    board = await create_initial_board()
    player = "white"

    for i, (start, end) in enumerate(parsed_moves):
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


async def cleanup_board(game_id: str):
    keys = await redis_client.keys(f"{HOTSEAT_REDIS_KEY_PREFIX}:{game_id}:*")
    if keys:
        await redis_client.delete(*keys)
    user_keys = await redis_client.keys(f"{USER_HOTSEAT_KEY_PREFIX}:*")
    for key in user_keys:
        val = await redis_client.get(key)
        if val == game_id:
            await redis_client.delete(key)

async def expire_board(game_id: str, delay: int = 300):
    keys = await redis_client.keys(f"{HOTSEAT_REDIS_KEY_PREFIX}:{game_id}:*")
    for key in keys:
        await redis_client.expire(key, delay)
    user_keys = await redis_client.keys(f"{USER_HOTSEAT_KEY_PREFIX}:*")
    for key in user_keys:
        val = await redis_client.get(key)
        if val == game_id:
            await redis_client.expire(key, delay)

async def get_game_user(game_id: str) -> str | None:
    keys = await redis_client.keys(f"{USER_HOTSEAT_KEY_PREFIX}:*")
    for key in keys:
        val = await redis_client.get(key)
        if val == game_id:
            return key.split(":", 1)[1]
    return None
import json
import logging
import time
import uuid
from typing import Any, List, Tuple

import redis.asyncio as redis

from src.app.game.game_logic import Board, create_initial_board, rebuild_board_from_history
from src.app.game.draw_logic import initial_draw_state
from src.app.utils.guest import is_guest
from src.base import redis_keys as keys
from src.base.redis_names import user_folder, user_id_from_folder
from src.settings.config import redis_db, redis_host, redis_password, redis_port, redis_user

redis_client = redis.Redis(
    host=redis_host,
    port=redis_port,
    db=redis_db,
    username=redis_user,
    password=redis_password,
    decode_responses=True,
)

STATE_KEY = "state"
HISTORY_KEY_PREFIX = "history"
TIMER_KEY_PREFIX = "timer"
PLAYERS_KEY = "players"
CHAIN_KEY_PREFIX = "chain"
DRAW_OFFER_KEY_PREFIX = "draw_offer"
DRAW_STATE_KEY_PREFIX = "draw_state"
DEFAULT_TIME = 600
WAITING_TIMEOUT = 600
CHAT_PREFIX = "users"
LOBBY_CHAT_PREFIX = "lobby_chat"
MOVE_INPUT_MODE_SETTING = "move_input_mode"
MOVE_INPUT_MODES = {"click", "drag"}
MULTIPLAYER_FIELDS = (
    STATE_KEY,
    HISTORY_KEY_PREFIX,
    TIMER_KEY_PREFIX,
    PLAYERS_KEY,
    CHAIN_KEY_PREFIX,
    DRAW_OFFER_KEY_PREFIX,
    DRAW_STATE_KEY_PREFIX,
)

logger = logging.getLogger(__name__)


async def _matching_keys(pattern: str) -> list[str]:
    return [key async for key in redis_client.scan_iter(match=pattern)]


async def _move_key(src: str, dst: str) -> None:
    if src == dst or not await redis_client.exists(src):
        return
    if await redis_client.exists(dst):
        await redis_client.delete(src)
        return
    await redis_client.rename(src, dst)


async def _move_matching_keys(pattern: str, old_prefix: str, new_prefix: str) -> None:
    for key in await _matching_keys(pattern):
        if key.startswith(old_prefix):
            await _move_key(key, new_prefix + key[len(old_prefix):])


async def _move_multiplayer_game(board_id: str, old_owner: str, new_owner: str) -> None:
    old_prefix = keys.multiplayer_game_key(old_owner, board_id, "")
    new_prefix = keys.multiplayer_game_key(new_owner, board_id, "")
    await _move_matching_keys(
        keys.multiplayer_game_pattern(old_owner, board_id),
        old_prefix,
        new_prefix,
    )


async def _multiplayer_owner(board_id: str) -> str:
    return await redis_client.get(keys.multiplayer_owner_key(board_id)) or keys.ORPHAN_USER


async def _set_multiplayer_owner(board_id: str, owner: str) -> None:
    old_owner = await _multiplayer_owner(board_id)
    if old_owner != owner:
        await _move_multiplayer_game(board_id, old_owner, owner)
    await redis_client.set(keys.multiplayer_owner_key(board_id), owner)


async def _board_field_key(board_id: str, field: str) -> str:
    owner = await _multiplayer_owner(board_id)
    return keys.multiplayer_game_key(owner, board_id, field)


async def get_board_storage_keys(board_id: str) -> dict[str, str]:
    owner = await _multiplayer_owner(board_id)
    return {
        "state": keys.multiplayer_game_key(owner, board_id, STATE_KEY),
        "history": keys.multiplayer_game_key(owner, board_id, HISTORY_KEY_PREFIX),
        "timer": keys.multiplayer_game_key(owner, board_id, TIMER_KEY_PREFIX),
        "players": keys.multiplayer_game_key(owner, board_id, PLAYERS_KEY),
        "chain": keys.multiplayer_game_key(owner, board_id, CHAIN_KEY_PREFIX),
        "draw": keys.multiplayer_game_key(owner, board_id, DRAW_STATE_KEY_PREFIX),
        "draw_offer": keys.multiplayer_game_key(owner, board_id, DRAW_OFFER_KEY_PREFIX),
    }


def normalize_move_input_mode(mode: str | None) -> str:
    return mode if mode in MOVE_INPUT_MODES else "click"


async def _user_setting_key(user_id: str | int, setting: str) -> str:
    return keys.user_setting_key(await user_folder(user_id), setting)


async def _multiplayer_active_key(user_id: str | int) -> str:
    return keys.multiplayer_active_key(await user_folder(user_id))


async def _multiplayer_ref_key(user_id: str | int, board_id: str) -> str:
    return keys.multiplayer_ref_key(await user_folder(user_id), board_id)


async def _hotseat_active_key(user_id: str | int) -> str:
    return keys.hotseat_active_key(await user_folder(user_id))


async def _waiting_since_key(user_id: str | int) -> str:
    return keys.waiting_since_key(await user_folder(user_id))


async def _rematch_user_invite_key(user_id: str | int, board_id: str) -> str:
    return keys.rematch_user_invite_key(await user_folder(user_id), board_id)


async def _rematch_user_invites_pattern(user_id: str | int) -> str:
    return keys.rematch_user_invites_pattern(await user_folder(user_id))


def _waiting_key(username: str) -> str:
    return keys.waiting_queue_key(username)


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
    return bool(await redis_client.exists(await _board_field_key(board_id, STATE_KEY)))


async def get_board_state(board_id: str, create: bool = True):
    key = await _board_field_key(board_id, STATE_KEY)
    raw = await redis_client.get(key)
    if not raw:
        if not create:
            return None
        board = create_initial_board()
        draw_key = await _board_field_key(board_id, DRAW_STATE_KEY_PREFIX)
        pipe = redis_client.pipeline(transaction=True)
        pipe.set(key, json.dumps(board))
        pipe.set(draw_key, json.dumps(initial_draw_state(board)))
        await pipe.execute()
        return board
    return json.loads(raw)


async def save_board_state(board_id: str, board):
    await redis_client.set(await _board_field_key(board_id, STATE_KEY), json.dumps(board))


async def assign_user_board(username: str, board_id: str):
    await redis_client.set(await _multiplayer_active_key(username), board_id)
    owner = await _multiplayer_owner(board_id)
    if owner != keys.ORPHAN_USER:
        await redis_client.set(await _multiplayer_ref_key(username, board_id), owner)


async def assign_user_hotseat(username: str, board_id: str):
    owner = await user_folder(username)
    await redis_client.set(await _hotseat_active_key(username), board_id)
    old_owner = await redis_client.get(keys.hotseat_owner_key(board_id)) or keys.ORPHAN_USER
    if old_owner != owner:
        old_prefix = keys.hotseat_game_key(old_owner, board_id, "")
        new_prefix = keys.hotseat_game_key(owner, board_id, "")
        await _move_matching_keys(keys.hotseat_game_pattern(old_owner, board_id), old_prefix, new_prefix)
    await redis_client.set(keys.hotseat_owner_key(board_id), owner)


async def set_board_players(board_id: str, players: dict):
    player_ids = [str(uid) for uid in players.values() if uid is not None]
    has_guest = any(is_guest(uid) for uid in player_ids)
    has_registered = any(not is_guest(uid) for uid in player_ids)
    if has_guest and has_registered:
        raise ValueError("ghost users cannot play with registered users")
    owner = await user_folder(str(players.get("white") or player_ids[0]))
    await _set_multiplayer_owner(board_id, owner)
    pipe = redis_client.pipeline(transaction=True)
    pipe.set(keys.multiplayer_game_key(owner, board_id, PLAYERS_KEY), json.dumps(players))
    for uid in player_ids:
        folder = await user_folder(uid)
        pipe.set(keys.multiplayer_active_key(folder), board_id)
        pipe.set(keys.multiplayer_ref_key(folder, board_id), owner)
    await pipe.execute()


async def get_board_players(board_id: str):
    raw = await redis_client.get(await _board_field_key(board_id, PLAYERS_KEY))
    return json.loads(raw) if raw else None


async def get_user_board(username: str):
    return await redis_client.get(await _multiplayer_active_key(username))


async def get_user_hotseat(username: str):
    return await redis_client.get(await _hotseat_active_key(username))


async def clear_user_hotseat(username: str):
    await redis_client.delete(await _hotseat_active_key(username))


async def get_history(board_id: str):
    raw = await redis_client.lrange(await _board_field_key(board_id, HISTORY_KEY_PREFIX), 0, -1)
    return raw if raw is not None else []


async def append_history(board_id: str, move: str):
    await redis_client.rpush(await _board_field_key(board_id, HISTORY_KEY_PREFIX), move)


async def _resume_if_draw_offer_expired(board_id: str, timers: dict[str, Any]) -> dict[str, Any]:
    if timers.get("turn") != "paused":
        return timers
    offer_exists = await redis_client.exists(await _board_field_key(board_id, DRAW_OFFER_KEY_PREFIX))
    if offer_exists:
        return timers
    timers["turn"] = timers.get("paused_turn") if timers.get("paused_turn") in ("white", "black") else "white"
    timers.pop("paused_turn", None)
    timers["last_ts"] = time.time()
    await redis_client.set(await _board_field_key(board_id, TIMER_KEY_PREFIX), json.dumps(timers))
    return timers


async def _read_timers(board_id: str, create: bool = True):
    key = await _board_field_key(board_id, TIMER_KEY_PREFIX)
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
    timers = json.loads(raw)
    return await _resume_if_draw_offer_expired(board_id, timers)


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
    await redis_client.set(await _board_field_key(board_id, TIMER_KEY_PREFIX), json.dumps(timers))
    return timers


async def apply_same_turn_timer(board_id: str, player: str):
    timers = await _read_timers(board_id)
    now = time.time()
    elapsed = now - timers["last_ts"]
    timers[player] = max(0, timers[player] - elapsed)
    timers["last_ts"] = now
    await redis_client.set(await _board_field_key(board_id, TIMER_KEY_PREFIX), json.dumps(timers))
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
    timers.pop("paused_turn", None)
    await redis_client.set(await _board_field_key(board_id, TIMER_KEY_PREFIX), json.dumps(timers))
    return timers


async def pause_timers(board_id: str):
    timers = await _read_timers(board_id, create=False)
    if timers is None:
        return None
    turn = timers.get("turn")
    if turn in ("white", "black"):
        now = time.time()
        elapsed = now - timers["last_ts"]
        timers[turn] = max(0, timers[turn] - elapsed)
        timers["paused_turn"] = turn
        timers["turn"] = "paused"
        timers["last_ts"] = now
        await redis_client.set(await _board_field_key(board_id, TIMER_KEY_PREFIX), json.dumps(timers))
    return timers


async def resume_timers(board_id: str):
    timers = await _read_timers(board_id, create=False)
    if timers is None:
        return None
    if timers.get("turn") == "paused":
        timers["turn"] = timers.get("paused_turn") if timers.get("paused_turn") in ("white", "black") else "white"
        timers.pop("paused_turn", None)
        timers["last_ts"] = time.time()
        await redis_client.set(await _board_field_key(board_id, TIMER_KEY_PREFIX), json.dumps(timers))
    return timers


async def get_chain_state(board_id: str) -> dict[str, Any] | None:
    raw = await redis_client.get(await _board_field_key(board_id, CHAIN_KEY_PREFIX))
    return json.loads(raw) if raw else None


async def save_chain_state(board_id: str, state: dict[str, Any] | None) -> None:
    key = await _board_field_key(board_id, CHAIN_KEY_PREFIX)
    if state is None:
        await redis_client.delete(key)
        return
    await redis_client.set(key, json.dumps(state))


async def clear_chain_state(board_id: str) -> None:
    await redis_client.delete(await _board_field_key(board_id, CHAIN_KEY_PREFIX))


async def get_draw_state(board_id: str) -> dict[str, Any] | None:
    raw = await redis_client.get(await _board_field_key(board_id, DRAW_STATE_KEY_PREFIX))
    return json.loads(raw) if raw else None


async def save_draw_state(board_id: str, state: dict[str, Any] | None) -> None:
    key = await _board_field_key(board_id, DRAW_STATE_KEY_PREFIX)
    if state is None:
        await redis_client.delete(key)
        return
    await redis_client.set(key, json.dumps(state))


async def clear_draw_state(board_id: str) -> None:
    await redis_client.delete(await _board_field_key(board_id, DRAW_STATE_KEY_PREFIX))


async def get_user_move_input_mode(user_id: str | int | None) -> str:
    if not user_id:
        return "click"
    raw = await redis_client.get(await _user_setting_key(user_id, MOVE_INPUT_MODE_SETTING))
    return normalize_move_input_mode(raw)


async def set_user_move_input_mode(user_id: str | int, mode: str | None) -> str:
    normalized = normalize_move_input_mode(mode)
    await redis_client.set(await _user_setting_key(user_id, MOVE_INPUT_MODE_SETTING), normalized)
    return normalized


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
        await redis_client.delete(await _waiting_since_key(waiting))
        await set_board_players(board_id, {"white": waiting, "black": username})
        return board_id, "black"
    if waiting == username:
        return None, None
    await redis_client.set(wkey, username, ex=WAITING_TIMEOUT)
    await redis_client.set(await _waiting_since_key(username), time.time(), ex=WAITING_TIMEOUT)
    return None, None


async def check_waiting(username: str):
    board_id = await get_user_board(username)
    if board_id:
        players = await get_board_players(board_id)
        if players:
            color = "white" if players.get("white") == username else "black"
            return board_id, color
        else:
            await redis_client.delete(await _multiplayer_active_key(username))
    if await waiting_timed_out(username):
        return None, None
    return None, None


async def get_waiting_time(username: str):
    ts = await redis_client.get(await _waiting_since_key(username))
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
        await redis_client.delete(await _waiting_since_key(username))
    await redis_client.delete(await _multiplayer_active_key(username))


async def cleanup_board(board_id: str):
    owner = await _multiplayer_owner(board_id)
    players = await get_board_players(board_id) or {}
    for user in players.values():
        await redis_client.delete(await _multiplayer_active_key(user))
        await redis_client.delete(await _hotseat_active_key(user))
        await redis_client.delete(await _multiplayer_ref_key(user, board_id))
        await redis_client.delete(await _rematch_user_invite_key(user, board_id))
    game_keys = await _matching_keys(keys.multiplayer_game_pattern(owner, board_id))
    index_keys = [keys.multiplayer_owner_key(board_id)]
    if game_keys or index_keys:
        await redis_client.delete(*(game_keys + index_keys))


async def expire_board(board_id: str, delay: int = 300):
    owner = await _multiplayer_owner(board_id)
    players = await get_board_players(board_id) or {}
    actual_delay = delay
    if any(is_guest(str(user)) for user in players.values()):
        actual_delay = max(delay, keys.GUEST_FINISHED_GAME_TTL_SECONDS)
    for user in players.values():
        await redis_client.delete(await _multiplayer_active_key(user))
        await redis_client.delete(await _hotseat_active_key(user))
        await redis_client.expire(await _multiplayer_ref_key(user, board_id), actual_delay)
        await redis_client.expire(await _rematch_user_invite_key(user, board_id), keys.REQUEST_TTL_SECONDS)
    for key in await _matching_keys(keys.multiplayer_game_pattern(owner, board_id)):
        await redis_client.expire(key, actual_delay)
    await redis_client.expire(keys.multiplayer_owner_key(board_id), actual_delay)


async def set_draw_offer(board_id: str, player: str) -> bool:
    key = await _board_field_key(board_id, DRAW_OFFER_KEY_PREFIX)
    data = {"from": player, "pending": True, "created_at": time.time()}
    return bool(
        await redis_client.set(
            key,
            json.dumps(data),
            nx=True,
            ex=keys.REQUEST_TTL_SECONDS,
        )
    )


async def get_draw_offer(board_id: str):
    key = await _board_field_key(board_id, DRAW_OFFER_KEY_PREFIX)
    raw = await redis_client.get(key)
    if not raw:
        return None
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    return {"from": raw, "pending": True}


async def mark_draw_offer_resolved(board_id: str):
    key = await _board_field_key(board_id, DRAW_OFFER_KEY_PREFIX)
    offer = await get_draw_offer(board_id)
    if not offer:
        return
    offer["pending"] = False
    offer["resolved_at"] = time.time()
    await redis_client.set(key, json.dumps(offer))


async def clear_draw_offer(board_id: str):
    await redis_client.delete(await _board_field_key(board_id, DRAW_OFFER_KEY_PREFIX))


def _chat_id(user1: int, user2: int) -> str:
    a, b = sorted([int(user1), int(user2)])
    return f"{a}:{b}"


async def save_chat_message(sender_id: int, receiver_id: int, text: str):
    cid = _chat_id(sender_id, receiver_id)
    msg = {"sender": sender_id, "text": text, "ts": time.time()}
    owner, other = sorted([int(sender_id), int(receiver_id)])
    owner_folder = await user_folder(owner)
    await redis_client.rpush(f"{keys.user_root(owner_folder)}:chats:{other}:messages", json.dumps(msg))
    return cid, msg


async def get_chat_messages(user1: int, user2: int, limit: int = 50):
    cid = _chat_id(user1, user2)
    owner, other = sorted([int(user1), int(user2)])
    owner_folder = await user_folder(owner)
    raw = await redis_client.lrange(f"{keys.user_root(owner_folder)}:chats:{other}:messages", -limit, -1)
    msgs = [json.loads(m) for m in raw]
    return cid, msgs


async def get_user_chats(user_id: int) -> List[str]:
    cids = set()
    folder = await user_folder(user_id)
    for pattern in (
        f"{keys.user_root(folder)}:chats:*:messages",
        f"{keys.USERS_ROOT}:*:chats:{int(user_id)}:messages",
    ):
        for key in await _matching_keys(pattern):
            parts = key.split(":")
            if len(parts) >= 5 and parts[0] == "users" and parts[2] == "chats":
                if parts[1] == folder:
                    cids.add(_chat_id(int(user_id), int(parts[3])))
                else:
                    resolved = await user_id_from_folder(parts[1])
                    if resolved and str(resolved).isdigit():
                        cids.add(_chat_id(int(resolved), int(user_id)))
    return sorted(cids)


async def delete_chat(user1: int, user2: int) -> None:
    owner, other = sorted([int(user1), int(user2)])
    owner_folder = await user_folder(owner)
    await redis_client.delete(f"{keys.user_root(owner_folder)}:chats:{other}:messages")


async def _lobby_owner(lobby_id: str) -> str:
    return await redis_client.get(keys.lobby_owner_key(lobby_id)) or keys.ORPHAN_USER


async def save_lobby_chat_message(lobby_id: str, sender: int, text: str):
    owner = await _lobby_owner(lobby_id)
    msg = {"sender": sender, "text": text, "ts": time.time()}
    await redis_client.rpush(keys.lobby_key(owner, lobby_id, "chat"), json.dumps(msg))
    return msg


async def get_lobby_chat_messages(lobby_id: str, limit: int = 50):
    owner = await _lobby_owner(lobby_id)
    raw = await redis_client.lrange(keys.lobby_key(owner, lobby_id, "chat"), -limit, -1)
    return [json.loads(m) for m in raw]


async def clear_lobby_chat(lobby_id: str):
    owner = await _lobby_owner(lobby_id)
    await redis_client.delete(keys.lobby_key(owner, lobby_id, "chat"))


async def add_rematch_invite(board_id: str, to_id: str, from_id: str) -> bool:
    owner = await _multiplayer_owner(board_id)
    state_key = keys.rematch_state_key(owner, board_id)
    state = {
        "from": from_id,
        "to": to_id,
        "status": "pending",
        "created_at": time.time(),
    }
    created = await redis_client.set(
        state_key,
        json.dumps(state),
        nx=True,
        ex=keys.REQUEST_TTL_SECONDS,
    )
    if not created:
        return False
    pipe = redis_client.pipeline(transaction=True)
    to_folder = await user_folder(to_id)
    pipe.set(
        keys.rematch_board_invite_key(owner, board_id, to_folder),
        from_id,
        ex=keys.REQUEST_TTL_SECONDS,
    )
    pipe.set(
        await _rematch_user_invite_key(to_id, board_id),
        from_id,
        ex=keys.REQUEST_TTL_SECONDS,
    )
    await pipe.execute()
    return True


async def mark_rematch_invite_resolved(board_id: str, status: str) -> None:
    owner = await _multiplayer_owner(board_id)
    state_key = keys.rematch_state_key(owner, board_id)
    raw = await redis_client.get(state_key)
    if not raw:
        return
    try:
        state = json.loads(raw)
    except json.JSONDecodeError:
        state = {}
    state["status"] = status
    state["resolved_at"] = time.time()
    await redis_client.set(state_key, json.dumps(state), ex=keys.REQUEST_TTL_SECONDS)


async def remove_rematch_invite(board_id: str, user_id: str) -> None:
    owner = await _multiplayer_owner(board_id)
    user = await user_folder(user_id)
    await redis_client.delete(
        keys.rematch_board_invite_key(owner, board_id, user),
        await _rematch_user_invite_key(user_id, board_id),
    )


async def get_user_rematch_invites(user_id: str) -> dict:
    result = {}
    folder = await user_folder(user_id)
    prefix = keys.rematch_user_invite_key(folder, "")
    for key in await _matching_keys(keys.rematch_user_invites_pattern(folder)):
        board_id = key[len(prefix):]
        from_id = await redis_client.get(key)
        if from_id:
            result[board_id] = from_id
    return result


async def get_board_rematch_invites(board_id: str) -> dict:
    owner = await _multiplayer_owner(board_id)
    result = {}
    prefix = keys.rematch_board_invite_key(owner, board_id, "")
    for key in await _matching_keys(keys.rematch_board_invites_pattern(owner, board_id)):
        user_id = await user_id_from_folder(key[len(prefix):])
        from_id = await redis_client.get(key)
        if from_id and user_id:
            result[user_id] = from_id
    return result

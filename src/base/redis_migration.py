import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import asyncpg
from dotenv import load_dotenv
import redis

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.app.utils.guest import is_guest
from src.base import redis_keys as keys

load_dotenv(ROOT / ".env")

REQUEST_TTL_SECONDS = keys.REQUEST_TTL_SECONDS
GUEST_TTL_SECONDS = keys.GUEST_FINISHED_GAME_TTL_SECONDS
WAITING_TIMEOUT_SECONDS = 600
ID_TO_LOGIN: dict[str, str] = {}
OLD_PREFIXES = (
    "board:*",
    "single_board:*",
    "single_user_game:*",
    "single_game_user:*",
    "hotseat_board:*",
    "user_board:*",
    "user_hotseat:*",
    "lobby:*",
    "user_lobby:*",
    "lobby_invites:*",
    "user_invites:*",
    "lobby_chat:*",
    "rematch_invites:*",
    "user_rematch:*",
    "rematch_request_state:*",
    "user_move_input_mode:*",
    "sess:*",
    "user_sess:*",
    "chats:*",
    "waiting_user_reg",
    "waiting_user_guest",
    "waiting_time_reg:*",
    "waiting_time_guest:*",
)


def redis_client() -> redis.Redis:
    return redis.Redis(
        host=os.environ["REDIS_HOST"],
        port=int(os.environ["REDIS_PORT"]),
        db=int(os.environ["REDIS_DB"]),
        username=os.environ.get("REDIS_USER") or None,
        password=os.environ.get("REDIS_PASSWORD") or None,
        decode_responses=True,
    )


async def _load_user_folders() -> dict[str, str]:
    conn = await asyncpg.connect(
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASS"],
        database=os.environ["DB_NAME"],
        host=os.environ["DB_HOST"],
        port=int(os.environ["DB_PORT"]),
    )
    rows = await conn.fetch("select id, login from users")
    await conn.close()
    return {str(row["id"]): row["login"] for row in rows}


def load_user_folders() -> None:
    global ID_TO_LOGIN
    ID_TO_LOGIN = asyncio.run(_load_user_folders())


def user_folder(user_id: str | int | None) -> str:
    raw = "" if user_id is None else str(user_id)
    if not raw:
        return keys.ORPHAN_USER
    if is_guest(raw) or not raw.isdigit():
        return raw
    return ID_TO_LOGIN.get(raw) or f"deleted_user_{raw}"


def user_id_from_folder(folder: str) -> str:
    if folder.startswith("deleted_user_") and folder.removeprefix("deleted_user_").isdigit():
        return folder.removeprefix("deleted_user_")
    for user_id, login in ID_TO_LOGIN.items():
        if login == folder:
            return user_id
    return folder


def chat_messages_key(user1: int | str, user2: int | str) -> str:
    a, b = sorted([int(user1), int(user2)])
    return f"{keys.user_root(user_folder(a))}:chats:{b}:messages"


def all_keys(r: redis.Redis, pattern: str = "*") -> list[str]:
    return sorted(r.scan_iter(pattern))


def ttl_to_apply(r: redis.Redis, src: str, override: int | None = None) -> int | None:
    if override is not None:
        return override
    ttl = r.ttl(src)
    return ttl if ttl and ttl > 0 else None


def dump_value(r: redis.Redis, key: str) -> dict[str, Any]:
    key_type = r.type(key)
    payload: Any
    if key_type == "string":
        payload = r.get(key)
    elif key_type == "list":
        payload = r.lrange(key, 0, -1)
    elif key_type == "set":
        payload = sorted(r.smembers(key))
    elif key_type == "zset":
        payload = r.zrange(key, 0, -1, withscores=True)
    elif key_type == "hash":
        payload = r.hgetall(key)
    else:
        payload = None
    return {"type": key_type, "ttl": r.ttl(key), "value": payload}


def write_backup(r: redis.Redis) -> Path:
    backup_dir = ROOT / "redis_backups"
    backup_dir.mkdir(exist_ok=True)
    path = backup_dir / f"redis_before_users_schema_{time.strftime('%Y%m%d_%H%M%S')}.json"
    payload = {key: dump_value(r, key) for key in all_keys(r)}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def set_ttl(r: redis.Redis, dst: str, ttl: int | None) -> None:
    if ttl is not None:
        r.expire(dst, ttl)


def copy_key(
    r: redis.Redis,
    src: str,
    dst: str,
    *,
    ttl_override: int | None = None,
    history_as_list: bool = False,
) -> bool:
    if not r.exists(src):
        return False
    key_type = r.type(src)
    ttl = ttl_to_apply(r, src, ttl_override)
    r.delete(dst)
    if key_type == "string":
        raw = r.get(src)
        if history_as_list:
            try:
                parsed = json.loads(raw or "[]")
            except json.JSONDecodeError:
                parsed = []
            if isinstance(parsed, list):
                if parsed:
                    r.rpush(dst, *parsed)
                set_ttl(r, dst, ttl)
                return True
        r.set(dst, raw)
    elif key_type == "list":
        values = r.lrange(src, 0, -1)
        if values:
            r.rpush(dst, *values)
    elif key_type == "set":
        values = r.smembers(src)
        if values:
            r.sadd(dst, *values)
    elif key_type == "hash":
        values = r.hgetall(src)
        if values:
            r.hset(dst, mapping=values)
    elif key_type == "zset":
        values = r.zrange(src, 0, -1, withscores=True)
        if values:
            r.zadd(dst, dict(values))
    else:
        return False
    set_ttl(r, dst, ttl)
    return True


def read_json(r: redis.Redis, key: str, default: Any) -> Any:
    raw = r.get(key)
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


def game_ttl_for_users(users: list[str], fallback: int | None = None) -> int | None:
    return GUEST_TTL_SECONDS if any(is_guest(user) for user in users) else fallback


def migrate_sessions(r: redis.Redis) -> int:
    changed = 0
    token_owners: dict[str, set[str]] = {}
    for key in all_keys(r, "user_sess:*"):
        user_id = key.split(":", 1)[1]
        folder = user_folder(user_id)
        tokens = r.smembers(key)
        if tokens:
            r.sadd(keys.user_sessions_key(folder), *tokens)
            changed += 1
        for token in tokens:
            token_owners.setdefault(token, set()).add(folder)
    for key in all_keys(r, "sess:*"):
        token = key.split(":", 1)[1]
        owners = token_owners.get(token) or {keys.ORPHAN_USER}
        for folder in owners:
            if copy_key(r, key, keys.session_key(folder, token)):
                changed += 1
    return changed


def migrate_settings(r: redis.Redis) -> int:
    changed = 0
    for key in all_keys(r, "user_move_input_mode:*"):
        user_id = key.split(":", 1)[1]
        if copy_key(r, key, keys.user_setting_key(user_folder(user_id), "move_input_mode")):
            changed += 1
    return changed


def migrate_chats(r: redis.Redis) -> int:
    changed = 0
    for key in all_keys(r, "chats:*"):
        _, a, b = key.split(":", 2)
        if copy_key(r, key, chat_messages_key(a, b)):
            changed += 1
    return changed


def migrate_lobbies(r: redis.Redis) -> int:
    changed = 0
    lobby_owners: dict[str, str] = {}
    for key in all_keys(r, "lobby:*"):
        lobby_id = key.split(":", 1)[1]
        lobby = read_json(r, key, {})
        owner = user_folder(lobby.get("host") or keys.ORPHAN_USER)
        lobby_owners[lobby_id] = owner
        r.set(keys.lobby_owner_key(lobby_id), owner)
        if copy_key(r, key, keys.lobby_key(owner, lobby_id, "info")):
            changed += 1
        for uid in lobby.get("players", []):
            r.set(keys.lobby_active_key(user_folder(uid)), lobby_id)
            changed += 1
    for key in all_keys(r, "user_lobby:*"):
        user_id = key.split(":", 1)[1]
        lobby_id = r.get(key)
        if lobby_id:
            r.set(keys.lobby_active_key(user_folder(user_id)), lobby_id)
            changed += 1
    for key in all_keys(r, "lobby_chat:*"):
        lobby_id = key.split(":", 1)[1]
        owner = lobby_owners.get(lobby_id) or r.get(keys.lobby_owner_key(lobby_id)) or keys.ORPHAN_USER
        if copy_key(r, key, keys.lobby_key(owner, lobby_id, "chat")):
            changed += 1
    for key in all_keys(r, "lobby_invites:*"):
        lobby_id = key.split(":", 1)[1]
        owner = lobby_owners.get(lobby_id) or r.get(keys.lobby_owner_key(lobby_id)) or keys.ORPHAN_USER
        for user_id, status in read_json(r, key, {}).items():
            r.set(keys.lobby_invite_status_key(owner, lobby_id, user_folder(user_id)), status, ex=REQUEST_TTL_SECONDS)
            changed += 1
    for key in all_keys(r, "user_invites:*"):
        user_id = key.split(":", 1)[1]
        for lobby_id, from_id in read_json(r, key, {}).items():
            r.set(keys.lobby_user_invite_key(user_folder(user_id), lobby_id), from_id, ex=REQUEST_TTL_SECONDS)
            changed += 1
    return changed


def multiplayer_owner(r: redis.Redis, board_id: str) -> tuple[str, dict[str, str]]:
    players = read_json(r, f"board:{board_id}:players", {})
    owner = user_folder(players.get("white") or next(iter(players.values()), keys.ORPHAN_USER))
    return owner, {str(k): str(v) for k, v in players.items()}


def migrate_multiplayer(r: redis.Redis) -> tuple[int, list[str]]:
    changed = 0
    warnings: list[str] = []
    board_ids = sorted({key.split(":")[1] for key in all_keys(r, "board:*") if key.count(":") >= 2})
    for board_id in board_ids:
        owner, players = multiplayer_owner(r, board_id)
        player_ids = list(players.values())
        if any(is_guest(uid) for uid in player_ids) and any(not is_guest(uid) for uid in player_ids):
            warnings.append(f"mixed guest/registered multiplayer board kept with TTL: {board_id}")
        r.set(keys.multiplayer_owner_key(board_id), owner)
        ttl = game_ttl_for_users(player_ids)
        for field in ("state", "history", "timer", "players", "chain", "draw_state", "draw_offer"):
            src = f"board:{board_id}:{field}"
            dst = keys.multiplayer_game_key(owner, board_id, field)
            field_ttl = REQUEST_TTL_SECONDS if field == "draw_offer" else ttl
            if copy_key(r, src, dst, ttl_override=field_ttl, history_as_list=(field == "history")):
                changed += 1
        if ttl:
            r.expire(keys.multiplayer_owner_key(board_id), ttl)
        for uid in player_ids:
            folder = user_folder(uid)
            r.set(keys.multiplayer_active_key(folder), board_id)
            r.set(keys.multiplayer_ref_key(folder, board_id), owner)
            if ttl:
                r.expire(keys.multiplayer_active_key(folder), ttl)
                r.expire(keys.multiplayer_ref_key(folder, board_id), ttl)
            changed += 1
    for key in all_keys(r, "user_board:*"):
        user_id = key.split(":", 1)[1]
        board_id = r.get(key)
        if not board_id:
            continue
        owner = r.get(keys.multiplayer_owner_key(board_id)) or keys.ORPHAN_USER
        folder = user_folder(user_id)
        ttl = GUEST_TTL_SECONDS if is_guest(user_id) else None
        r.set(keys.multiplayer_active_key(folder), board_id)
        r.set(keys.multiplayer_ref_key(folder, board_id), owner)
        if ttl:
            r.expire(keys.multiplayer_active_key(folder), ttl)
            r.expire(keys.multiplayer_ref_key(folder, board_id), ttl)
        changed += 1
    for key in all_keys(r, "rematch_invites:*"):
        board_id = key.split(":", 1)[1]
        owner = r.get(keys.multiplayer_owner_key(board_id)) or keys.ORPHAN_USER
        for user_id, from_id in read_json(r, key, {}).items():
            r.set(keys.rematch_board_invite_key(owner, board_id, user_folder(user_id)), from_id, ex=REQUEST_TTL_SECONDS)
            changed += 1
    for key in all_keys(r, "user_rematch:*"):
        user_id = key.split(":", 1)[1]
        for board_id, from_id in read_json(r, key, {}).items():
            r.set(keys.rematch_user_invite_key(user_folder(user_id), board_id), from_id, ex=REQUEST_TTL_SECONDS)
            changed += 1
    for key in all_keys(r, "rematch_request_state:*"):
        board_id = key.split(":", 1)[1]
        owner = r.get(keys.multiplayer_owner_key(board_id)) or keys.ORPHAN_USER
        if copy_key(r, key, keys.rematch_state_key(owner, board_id), ttl_override=REQUEST_TTL_SECONDS):
            changed += 1
    return changed, warnings


def migrate_single(r: redis.Redis) -> int:
    changed = 0
    owners = {
        key.split(":", 1)[1]: r.get(key)
        for key in all_keys(r, "single_game_user:*")
    }
    for key in all_keys(r, "single_user_game:*"):
        user_id = key.split(":", 1)[1]
        game_id = r.get(key)
        if game_id:
            owners.setdefault(game_id, user_id)
            folder = user_folder(user_id)
            r.set(keys.single_active_key(folder), game_id)
            if is_guest(user_id):
                r.expire(keys.single_active_key(folder), GUEST_TTL_SECONDS)
            changed += 1
    game_ids = sorted({key.split(":")[1] for key in all_keys(r, "single_board:*") if key.count(":") >= 2})
    for game_id in game_ids:
        owner_id = str(owners.get(game_id) or keys.ORPHAN_USER)
        owner = user_folder(owner_id)
        ttl = GUEST_TTL_SECONDS if is_guest(owner_id) else None
        r.set(keys.single_owner_key(game_id), owner)
        if ttl:
            r.expire(keys.single_owner_key(game_id), ttl)
        for field in ("state", "history", "timer", "chain", "draw_state"):
            if copy_key(
                r,
                f"single_board:{game_id}:{field}",
                keys.single_game_key(owner, game_id, field),
                ttl_override=ttl,
                history_as_list=(field == "history"),
            ):
                changed += 1
    return changed


def migrate_hotseat(r: redis.Redis) -> int:
    changed = 0
    owners: dict[str, str] = {}
    for key in all_keys(r, "user_hotseat:*"):
        user_id = key.split(":", 1)[1]
        game_id = r.get(key)
        if not game_id:
            continue
        owners.setdefault(game_id, user_id)
        folder = user_folder(user_id)
        r.set(keys.hotseat_active_key(folder), game_id)
        if is_guest(user_id):
            r.expire(keys.hotseat_active_key(folder), GUEST_TTL_SECONDS)
        changed += 1
    game_ids = sorted({key.split(":")[1] for key in all_keys(r, "hotseat_board:*") if key.count(":") >= 2})
    for game_id in game_ids:
        owner_id = owners.get(game_id) or keys.ORPHAN_USER
        owner = user_folder(owner_id)
        ttl = GUEST_TTL_SECONDS if is_guest(owner_id) else None
        r.set(keys.hotseat_owner_key(game_id), owner)
        if ttl:
            r.expire(keys.hotseat_owner_key(game_id), ttl)
        for field in ("state", "history", "timer", "chain", "draw_state"):
            if copy_key(
                r,
                f"hotseat_board:{game_id}:{field}",
                keys.hotseat_game_key(owner, game_id, field),
                ttl_override=ttl,
                history_as_list=(field == "history"),
            ):
                changed += 1
    return changed


def migrate_waiting(r: redis.Redis) -> int:
    changed = 0
    pairs = {
        "waiting_user_reg": keys.waiting_queue_key("1"),
        "waiting_user_guest": keys.waiting_queue_key("ghost_placeholder"),
    }
    for old_key, new_key in pairs.items():
        if copy_key(r, old_key, new_key, ttl_override=WAITING_TIMEOUT_SECONDS):
            changed += 1
    for pattern in ("waiting_time_reg:*", "waiting_time_guest:*"):
        for key in all_keys(r, pattern):
            user_id = key.split(":", 1)[1]
            if copy_key(r, key, keys.waiting_since_key(user_folder(user_id)), ttl_override=WAITING_TIMEOUT_SECONDS):
                changed += 1
    return changed


def delete_old_keys(r: redis.Redis) -> int:
    old = set()
    for pattern in OLD_PREFIXES:
        old.update(all_keys(r, pattern))
    if old:
        r.delete(*sorted(old))
    return len(old)


def main() -> None:
    keep_old = "--keep-old" in sys.argv
    r = redis_client()
    if not r.ping():
        raise RuntimeError("Redis ping failed")
    load_user_folders()
    backup_path = write_backup(r)
    changed = 0
    warnings: list[str] = []
    changed += migrate_sessions(r)
    changed += migrate_settings(r)
    changed += migrate_chats(r)
    changed += migrate_lobbies(r)
    multi_changed, multi_warnings = migrate_multiplayer(r)
    changed += multi_changed
    warnings.extend(multi_warnings)
    changed += migrate_single(r)
    changed += migrate_hotseat(r)
    changed += migrate_waiting(r)
    deleted = 0 if keep_old else delete_old_keys(r)
    print(json.dumps({
        "backup": str(backup_path),
        "new_or_updated_keys": changed,
        "deleted_old_keys": deleted,
        "dbsize": r.dbsize(),
        "warnings": warnings,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

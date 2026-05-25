import json
import logging
import uuid

from .redis import clear_lobby_chat, redis_client
from src.base import redis_keys as keys
from src.base.redis_names import user_folder, user_id_from_folder

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


async def _lobby_owner(lobby_id: str) -> str:
    return await redis_client.get(keys.lobby_owner_key(lobby_id)) or keys.ORPHAN_USER


async def _set_lobby_owner(lobby_id: str, owner: str) -> None:
    owner = await user_folder(owner)
    old_owner = await _lobby_owner(lobby_id)
    if old_owner != owner:
        old_prefix = keys.lobby_key(old_owner, lobby_id, "")
        new_prefix = keys.lobby_key(owner, lobby_id, "")
        for key in await _matching_keys(keys.lobby_pattern(old_owner, lobby_id)):
            if key.startswith(old_prefix):
                await _move_key(key, new_prefix + key[len(old_prefix):])
    await redis_client.set(keys.lobby_owner_key(lobby_id), owner)


async def create_lobby(user_id: str) -> str:
    lobby_id = str(uuid.uuid4())
    lobby = {
        "host": user_id,
        "players": [user_id],
        "board_id": None,
        "colors": {user_id: None},
    }
    await _set_lobby_owner(lobby_id, user_id)
    owner = await user_folder(user_id)
    pipe = redis_client.pipeline(transaction=True)
    pipe.set(keys.lobby_key(owner, lobby_id, "info"), json.dumps(lobby))
    pipe.set(keys.lobby_active_key(owner), lobby_id)
    await pipe.execute()
    return lobby_id


async def get_lobby(lobby_id: str) -> dict | None:
    owner = await _lobby_owner(lobby_id)
    raw = await redis_client.get(keys.lobby_key(owner, lobby_id, "info"))
    return json.loads(raw) if raw else None


async def set_lobby(lobby_id: str, lobby: dict) -> None:
    owner = await _lobby_owner(lobby_id)
    await redis_client.set(keys.lobby_key(owner, lobby_id, "info"), json.dumps(lobby))


async def get_user_lobby(user_id: str) -> str | None:
    return await redis_client.get(keys.lobby_active_key(await user_folder(user_id)))


async def add_player(lobby_id: str, user_id: str) -> None:
    lobby = await get_lobby(lobby_id)
    if not lobby:
        return
    if len(lobby.get("players", [])) >= 2:
        return
    if user_id not in lobby["players"]:
        await clear_lobby_chat(lobby_id)
        lobby["players"].append(user_id)
        colors = lobby.setdefault("colors", {})
        if user_id not in colors:
            colors[user_id] = None
        await set_lobby(lobby_id, lobby)
    await redis_client.set(keys.lobby_active_key(await user_folder(user_id)), lobby_id)


async def remove_player(lobby_id: str, user_id: str) -> None:
    lobby = await get_lobby(lobby_id)
    if not lobby:
        return
    if user_id in lobby["players"]:
        lobby["players"].remove(user_id)
        if "colors" in lobby:
            lobby["colors"].pop(user_id, None)
        await set_invite_status(lobby_id, user_id, None)
        await redis_client.delete(keys.lobby_active_key(await user_folder(user_id)))
        if not lobby["players"] or user_id == lobby["host"]:
            await delete_lobby(lobby_id)
            return
        await set_lobby(lobby_id, lobby)


async def delete_lobby(lobby_id: str) -> None:
    owner = await _lobby_owner(lobby_id)
    lobby = await get_lobby(lobby_id)
    if lobby:
        for uid in lobby.get("players", []):
            await redis_client.delete(keys.lobby_active_key(await user_folder(uid)))
    for status_key in await _matching_keys(keys.lobby_invite_status_pattern(owner, lobby_id)):
        invited_user = status_key.rsplit(":", 1)[-1]
        await redis_client.delete(keys.lobby_user_invite_key(await user_folder(invited_user), lobby_id))
    lobby_keys = await _matching_keys(keys.lobby_pattern(owner, lobby_id))
    if lobby_keys:
        await redis_client.delete(*lobby_keys)
    await redis_client.delete(keys.lobby_owner_key(lobby_id))


async def set_lobby_board(lobby_id: str, board_id: str) -> None:
    lobby = await get_lobby(lobby_id)
    if not lobby:
        return
    lobby["board_id"] = board_id
    await set_lobby(lobby_id, lobby)


async def set_lobby_host(lobby_id: str, user_id: str) -> None:
    lobby = await get_lobby(lobby_id)
    if not lobby:
        return
    if user_id not in lobby.get("players", []):
        return
    lobby["host"] = user_id
    await _set_lobby_owner(lobby_id, user_id)
    await set_lobby(lobby_id, lobby)


async def set_player_color(lobby_id: str, user_id: str, color: str | None) -> None:
    lobby = await get_lobby(lobby_id)
    if not lobby:
        return
    colors = lobby.setdefault("colors", {})
    colors[user_id] = color
    await set_lobby(lobby_id, lobby)


async def get_lobby_colors(lobby_id: str) -> dict:
    lobby = await get_lobby(lobby_id)
    if not lobby:
        return {}
    return lobby.get("colors", {})


async def add_lobby_invite(lobby_id: str, to_id: str, from_id: str) -> None:
    owner = await _lobby_owner(lobby_id)
    to_folder = await user_folder(to_id)
    pipe = redis_client.pipeline(transaction=True)
    pipe.set(
        keys.lobby_invite_status_key(owner, lobby_id, to_folder),
        "sent",
        ex=keys.REQUEST_TTL_SECONDS,
    )
    pipe.set(
        keys.lobby_user_invite_key(to_folder, lobby_id),
        from_id,
        ex=keys.REQUEST_TTL_SECONDS,
    )
    await pipe.execute()


async def set_invite_status(lobby_id: str, user_id: str, status: str | None) -> None:
    owner = await _lobby_owner(lobby_id)
    user = await user_folder(user_id)
    key = keys.lobby_invite_status_key(owner, lobby_id, user)
    if status is None:
        await redis_client.delete(key, keys.lobby_user_invite_key(user, lobby_id))
    else:
        await redis_client.set(key, status, ex=keys.REQUEST_TTL_SECONDS)


async def remove_user_invite(user_id: str, lobby_id: str) -> None:
    owner = await _lobby_owner(lobby_id)
    user = await user_folder(user_id)
    await redis_client.delete(
        keys.lobby_user_invite_key(user, lobby_id),
        keys.lobby_invite_status_key(owner, lobby_id, user),
    )


async def get_user_invites(user_id: str) -> dict:
    result = {}
    user = await user_folder(user_id)
    prefix = keys.lobby_user_invite_key(user, "")
    for key in await _matching_keys(keys.lobby_user_invites_pattern(user)):
        lobby_id = key[len(prefix):]
        from_id = await redis_client.get(key)
        if from_id:
            result[lobby_id] = from_id
    return result


async def get_lobby_invites(lobby_id: str) -> dict:
    owner = await _lobby_owner(lobby_id)
    result = {}
    prefix = keys.lobby_invite_status_key(owner, lobby_id, "")
    for key in await _matching_keys(keys.lobby_invite_status_pattern(owner, lobby_id)):
        user_id = await user_id_from_folder(key[len(prefix):])
        status = await redis_client.get(key)
        if status and user_id:
            result[user_id] = status
    return result


async def clear_lobby_board(board_id: str) -> None:
    for key in await _matching_keys("users:*:lobby:*:info"):
        raw = await redis_client.get(key)
        if not raw:
            continue
        lobby = json.loads(raw)
        if lobby.get("board_id") == board_id:
            lobby["board_id"] = None
            await redis_client.set(key, json.dumps(lobby))

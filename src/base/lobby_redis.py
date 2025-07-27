import json
import uuid
import logging
from .redis import (
    redis_client,
    clear_lobby_chat,
)
import json

LOBBY_PREFIX = "lobby"
USER_LOBBY_PREFIX = "user_lobby"
LOBBY_INVITES_PREFIX = "lobby_invites"
USER_INVITES_PREFIX = "user_invites"

logger = logging.getLogger(__name__)


async def create_lobby(user_id: str) -> str:
    lobby_id = str(uuid.uuid4())
    lobby = {
        "host": user_id,
        "players": [user_id],
        "board_id": None,
        "colors": {user_id: None},
    }
    await redis_client.set(f"{LOBBY_PREFIX}:{lobby_id}", json.dumps(lobby))
    await redis_client.set(f"{USER_LOBBY_PREFIX}:{user_id}", lobby_id)
    return lobby_id


async def get_lobby(lobby_id: str) -> dict | None:
    raw = await redis_client.get(f"{LOBBY_PREFIX}:{lobby_id}")
    return json.loads(raw) if raw else None


async def set_lobby(lobby_id: str, lobby: dict) -> None:
    await redis_client.set(f"{LOBBY_PREFIX}:{lobby_id}", json.dumps(lobby))


async def get_user_lobby(user_id: str) -> str | None:
    return await redis_client.get(f"{USER_LOBBY_PREFIX}:{user_id}")


async def add_player(lobby_id: str, user_id: str) -> None:
    lobby = await get_lobby(lobby_id)
    if not lobby:
        return
    if len(lobby.get("players", [])) >= 2:
        return
    if user_id not in lobby["players"]:
        lobby["players"].append(user_id)
        colors = lobby.setdefault("colors", {})
        if user_id not in colors:
            colors[user_id] = None
        await set_lobby(lobby_id, lobby)
    await redis_client.set(f"{USER_LOBBY_PREFIX}:{user_id}", lobby_id)


async def remove_player(lobby_id: str, user_id: str) -> None:
    lobby = await get_lobby(lobby_id)
    if not lobby:
        return
    if user_id in lobby["players"]:
        lobby["players"].remove(user_id)
        if "colors" in lobby:
            lobby["colors"].pop(user_id, None)
        await set_invite_status(lobby_id, user_id, None)
        await redis_client.delete(f"{USER_LOBBY_PREFIX}:{user_id}")
        if not lobby["players"] or user_id == lobby["host"]:
            await delete_lobby(lobby_id)
            return
        await set_lobby(lobby_id, lobby)


async def delete_lobby(lobby_id: str) -> None:
    lobby = await get_lobby(lobby_id)
    if not lobby:
        return
    for uid in lobby.get("players", []):
        await redis_client.delete(f"{USER_LOBBY_PREFIX}:{uid}")
    await redis_client.delete(f"{LOBBY_PREFIX}:{lobby_id}")
    await clear_lobby_chat(lobby_id)


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


async def _read_lobby_invites(lobby_id: str) -> dict:
    raw = await redis_client.get(f"{LOBBY_INVITES_PREFIX}:{lobby_id}")
    return json.loads(raw) if raw else {}


async def _write_lobby_invites(lobby_id: str, data: dict) -> None:
    await redis_client.set(f"{LOBBY_INVITES_PREFIX}:{lobby_id}", json.dumps(data))


async def _read_user_invites(user_id: str) -> dict:
    raw = await redis_client.get(f"{USER_INVITES_PREFIX}:{user_id}")
    return json.loads(raw) if raw else {}


async def _write_user_invites(user_id: str, data: dict) -> None:
    await redis_client.set(f"{USER_INVITES_PREFIX}:{user_id}", json.dumps(data))


async def add_lobby_invite(lobby_id: str, to_id: str, from_id: str) -> None:
    lobby_invites = await _read_lobby_invites(lobby_id)
    lobby_invites[to_id] = "sent"
    await _write_lobby_invites(lobby_id, lobby_invites)

    user_invites = await _read_user_invites(to_id)
    user_invites[lobby_id] = from_id
    await _write_user_invites(to_id, user_invites)


async def set_invite_status(lobby_id: str, user_id: str, status: str | None) -> None:
    lobby_invites = await _read_lobby_invites(lobby_id)
    if status is None:
        lobby_invites.pop(user_id, None)
    else:
        lobby_invites[user_id] = status
    await _write_lobby_invites(lobby_id, lobby_invites)


async def remove_user_invite(user_id: str, lobby_id: str) -> None:
    user_invites = await _read_user_invites(user_id)
    if lobby_id in user_invites:
        user_invites.pop(lobby_id)
        await _write_user_invites(user_id, user_invites)


async def get_user_invites(user_id: str) -> dict:
    return await _read_user_invites(user_id)


async def get_lobby_invites(lobby_id: str) -> dict:
    return await _read_lobby_invites(lobby_id)

async def clear_lobby_board(board_id: str) -> None:
    pattern = f"{LOBBY_PREFIX}:*"
    keys = await redis_client.keys(pattern)
    for key in keys:
        raw = await redis_client.get(key)
        if not raw:
            continue
        lobby = json.loads(raw)
        if lobby.get("board_id") == board_id:
            lobby["board_id"] = None
            await redis_client.set(key, json.dumps(lobby))

import json
import uuid
from typing import Optional, List, Dict

from user_agents import parse
from httpx import AsyncClient

from src.base.redis import redis_client
from src.base import redis_keys as keys
from src.base.redis_names import user_folder


async def _get_city(ip: str) -> str:
    try:
        if not ip or ip.startswith(("10.", "192.168.", "172.16.", "127.", "fc", "fd", "::1")):
            return ""
        async with AsyncClient(timeout=3) as client:
            r = await client.get(f"https://ipapi.co/{ip}/json")
            if r.status_code == 200:
                data = r.json()
                return data.get("city") or ""
    except Exception:
        pass
    return ""


def _session_update_manager():
    # Deferred import to avoid circular imports
    from src.app.routers.ws_router import session_update_manager
    return session_update_manager


def _session_kick_manager():
    # Deferred import to avoid circular imports
    from src.app.routers.ws_router import session_kick_manager
    return session_kick_manager


async def create_session(user_id: int, user_agent: str, ip: str) -> str:
    token = str(uuid.uuid4())
    city = await _get_city(ip)
    ua = parse(user_agent)
    data = {
        "browser": ua.browser.family,
        "device": "mobile" if ua.is_mobile else "pc",
        "agent": user_agent,
        "ip": ip,
        "city": city,
    }
    folder = await user_folder(user_id)
    await redis_client.set(keys.session_key(folder, token), json.dumps(data))
    await redis_client.sadd(keys.user_sessions_key(folder), token)

    await _session_update_manager().broadcast(str(user_id), json.dumps({"action": "update"}))
    return token


async def delete_session(user_id: int, token: str) -> None:
    folder = await user_folder(user_id)
    await redis_client.delete(keys.session_key(folder, token))
    await redis_client.srem(keys.user_sessions_key(folder), token)

    await _session_kick_manager().broadcast(token, json.dumps({"action": "logout"}))
    await _session_update_manager().broadcast(str(user_id), json.dumps({"action": "update"}))


async def delete_all_sessions(user_id: int, keep: Optional[str] = None) -> None:
    folder = await user_folder(user_id)
    tokens = await redis_client.smembers(keys.user_sessions_key(folder))
    tokens = [t.decode() if isinstance(t, (bytes, bytearray)) else t for t in tokens]

    for t in tokens:
        if keep and t == keep:
            continue
        await redis_client.delete(keys.session_key(folder, t))
        await _session_kick_manager().broadcast(t, json.dumps({"action": "logout"}))

    if keep:
        to_remove = [t for t in tokens if t != keep]
        if to_remove:
            await redis_client.srem(keys.user_sessions_key(folder), *to_remove)
        await redis_client.sadd(keys.user_sessions_key(folder), keep)
    else:
        if tokens:
            await redis_client.delete(keys.user_sessions_key(folder))

    await _session_update_manager().broadcast(str(user_id), json.dumps({"action": "update"}))


async def get_sessions(user_id: int) -> List[Dict]:
    folder = await user_folder(user_id)
    tokens = await redis_client.smembers(keys.user_sessions_key(folder))
    tokens = [t.decode() if isinstance(t, (bytes, bytearray)) else t for t in tokens]
    result = []
    for t in tokens:
        raw = await redis_client.get(keys.session_key(folder, t))
        if raw:
            d = json.loads(raw)
            d["id"] = t
            result.append(d)
    return result


async def session_is_valid(user_id: int, token: str) -> bool:
    if not token:
        return False
    folder = await user_folder(user_id)
    in_set = await redis_client.sismember(keys.user_sessions_key(folder), token)
    if not in_set:
        return False
    return bool(await redis_client.exists(keys.session_key(folder, token)))

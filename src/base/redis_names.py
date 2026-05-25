from src.app.utils.guest import is_guest
from src.base.postgres import get_user_id_by_login, get_user_login

_id_to_name_cache: dict[str, str] = {}
_name_to_id_cache: dict[str, str] = {}


async def user_folder(user_id: str | int | None) -> str:
    raw = "" if user_id is None else str(user_id)
    if not raw or is_guest(raw) or not raw.isdigit():
        return raw
    cached = _id_to_name_cache.get(raw)
    if cached:
        return cached
    login = await get_user_login(int(raw))
    folder = login or f"deleted_user_{raw}"
    _id_to_name_cache[raw] = folder
    if login:
        _name_to_id_cache[login] = raw
    return folder


async def user_id_from_folder(folder: str | int | None) -> str | None:
    raw = "" if folder is None else str(folder)
    if not raw:
        return None
    if is_guest(raw) or raw.isdigit():
        return raw
    if raw.startswith("deleted_user_") and raw.removeprefix("deleted_user_").isdigit():
        return raw.removeprefix("deleted_user_")
    cached = _name_to_id_cache.get(raw)
    if cached:
        return cached
    user_id = await get_user_id_by_login(raw)
    if user_id is None:
        return raw
    value = str(user_id)
    _name_to_id_cache[raw] = value
    _id_to_name_cache[value] = raw
    return value

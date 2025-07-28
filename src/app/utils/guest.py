import uuid
from typing import Union

from src.base.postgres import get_user_login


def generate_guest_id() -> str:
    return f"ghost_{uuid.uuid4().hex}"


def is_guest(user_id: str | int | None) -> bool:
    return isinstance(user_id, str) and user_id.startswith("ghost_")


async def get_display_name(user_id: Union[str, int]) -> str:
    uid_str = str(user_id)
    if uid_str.isdigit():
        login = await get_user_login(int(uid_str))
        return login or uid_str
    return uid_str
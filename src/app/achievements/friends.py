from .data import FRIEND_ACHIEVEMENTS
from src.base.postgres import get_friends, unlock_achievement


async def check_friend_achievements(user_id: int) -> None:
    friends = await get_friends(user_id)
    count = len(friends)
    for ach in FRIEND_ACHIEVEMENTS:
        if count >= ach["threshold"]:
            await unlock_achievement(user_id, ach["code"])
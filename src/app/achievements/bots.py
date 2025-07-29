from .data import BOT_ACHIEVEMENTS
from src.base.postgres import count_bot_results, unlock_achievement


async def check_bot_achievements(user_id: int, difficulty: str, result: str) -> None:
    for ach in BOT_ACHIEVEMENTS:
        level = ach.get("level")
        if result == "win" and level == difficulty:
            count = await count_bot_results(user_id, difficulty, "win")
            if count >= ach["threshold"]:
                await unlock_achievement(user_id, ach["code"])
        elif (
            result == "loss"
            and ach["code"] == "lose_to_easy_bot"
            and difficulty == "easy"
        ):
            await unlock_achievement(user_id, ach["code"])
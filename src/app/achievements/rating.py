from datetime import datetime, timedelta

from .data import RATING_ACHIEVEMENTS
from src.base.postgres import (
    get_user_stats,
    sum_elo_change_since,
    unlock_achievement,
)
from src.settings.config import MOSCOW_TZ


async def check_rating_achievements(user_id: int) -> None:
    stats = await get_user_stats(user_id)
    elo = stats["elo"]
    for ach in RATING_ACHIEVEMENTS:
        code = ach["code"]
        threshold = ach["threshold"]
        if code.startswith("rank_"):
            if elo >= threshold:
                await unlock_achievement(user_id, code)
        elif code == "elo_plus_100_day":
            since = datetime.now(tz=MOSCOW_TZ) - timedelta(days=1)
            gain = await sum_elo_change_since(user_id, since)
            if gain >= threshold:
                await unlock_achievement(user_id, code)
        elif code == "elo_plus_500_week":
            since = datetime.now(tz=MOSCOW_TZ) - timedelta(days=7)
            gain = await sum_elo_change_since(user_id, since)
            if gain >= threshold:
                await unlock_achievement(user_id, code)


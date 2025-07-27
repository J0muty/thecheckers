from typing import List, Tuple

RANK_THRESHOLDS: List[Tuple[int, str]] = [
    (0, "Новичок"),
    (300, "Бронза I"),
    (600, "Бронза II"),
    (900, "Бронза III"),
    (1500, "Серебро I"),
    (1800, "Серебро II"),
    (2100, "Серебро III"),
    (2500, "Золото I"),
    (2800, "Золото II"),
    (3100, "Золото III"),
    (3600, "Платина"),
    (4000, "Мастер"),
    (5000, "Гран Мастер"),
    (7000, "Чемпион"),
]


def calculate_rank(elo: int) -> str:
    """Return rank name for a given Elo rating."""
    rank = RANK_THRESHOLDS[0][1]
    for threshold, title in RANK_THRESHOLDS:
        if elo >= threshold:
            rank = title
        else:
            break
    return rank


def update_elo(current: int, opponent: int, result: str, k: int = 32) -> int:
    result_map = {"win": 1.0, "draw": 0.5, "loss": 0.0}
    score = result_map.get(result)
    if score is None:
        raise ValueError(f"Unknown result: {result}")
    expected = 1 / (1 + 10 ** ((opponent - current) / 400))
    new_elo = int(round(current + k * (score - expected)))
    return max(new_elo, 0)

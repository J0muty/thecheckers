from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True)
class EvaluationWeights:
    man_value: int = 100
    king_value: int = 320
    endgame_king_bonus: int = 35
    center: int = 8
    advancement: int = 7
    back_rank: int = 5
    connected: int = 6
    promotion_ready: int = 18
    mobility: int = 5
    capture_pressure: int = 28
    threatened_material: int = 1
    king_count: int = 32
    edge_penalty: int = 3
    endgame_king_count: int = 24
    endgame_mobility: int = 3
    piece_activity: int = 0
    king_mobility: int = 0
    trapped_piece: int = 0


@dataclass(frozen=True)
class BotProfile:
    name: str
    weights: EvaluationWeights
    description: str = ""


HARD_WEIGHTS = EvaluationWeights()

HARDCORE_WEIGHTS = EvaluationWeights(
    king_value=330,
    endgame_king_bonus=50,
    center=10,
    advancement=8,
    back_rank=7,
    connected=8,
    promotion_ready=26,
    mobility=6,
    capture_pressure=34,
    threatened_material=2,
    king_count=38,
    edge_penalty=2,
    endgame_king_count=34,
    endgame_mobility=5,
    piece_activity=4,
    king_mobility=3,
    trapped_piece=18,
)

PROFILES: dict[str, BotProfile] = {
    "easy": BotProfile("easy", HARD_WEIGHTS, "Random bot with forced captures."),
    "medium": BotProfile("medium", HARD_WEIGHTS, "Short tactical search."),
    "hard": BotProfile("hard", HARD_WEIGHTS, "Stable alpha-beta profile."),
    "hardcore": BotProfile("hardcore", HARDCORE_WEIGHTS, "Sharper positional profile for the strongest bot."),
}

PROFILE_ALIASES: dict[str, str] = {
    "expert": "hardcore",
}

TUNABLE_WEIGHT_FIELDS: tuple[str, ...] = (
    "king_value",
    "endgame_king_bonus",
    "center",
    "advancement",
    "back_rank",
    "connected",
    "promotion_ready",
    "mobility",
    "capture_pressure",
    "threatened_material",
    "king_count",
    "edge_penalty",
    "endgame_king_count",
    "endgame_mobility",
    "piece_activity",
    "king_mobility",
    "trapped_piece",
)


def profile_for_difficulty(difficulty: str) -> BotProfile:
    return PROFILES.get(normalize_difficulty(difficulty), PROFILES["hard"])


def normalize_difficulty(difficulty: str) -> str:
    return PROFILE_ALIASES.get(difficulty, difficulty)


def weights_to_dict(weights: EvaluationWeights) -> dict[str, int]:
    return asdict(weights)


def profile_to_dict(profile: BotProfile) -> dict[str, object]:
    return {
        "name": profile.name,
        "description": profile.description,
        "weights": weights_to_dict(profile.weights),
    }


def weights_from_mapping(data: Mapping[str, object], base: EvaluationWeights = HARD_WEIGHTS) -> EvaluationWeights:
    updates: dict[str, int] = {}
    for field in TUNABLE_WEIGHT_FIELDS:
        value = data.get(field)
        if value is None:
            continue
        updates[field] = int(value)
    return replace(base, **updates)


def profile_from_mapping(data: Mapping[str, object], base: BotProfile | None = None) -> BotProfile:
    fallback = base or PROFILES["hardcore"]
    raw_weights = data.get("weights", data)
    weights = weights_from_mapping(
        raw_weights if isinstance(raw_weights, Mapping) else {},
        fallback.weights,
    )
    return BotProfile(
        name=str(data.get("name", fallback.name)),
        description=str(data.get("description", fallback.description)),
        weights=weights,
    )


def load_profile(path: str | Path, base: BotProfile | None = None) -> BotProfile:
    with Path(path).open("r", encoding="utf-8") as f:
        return profile_from_mapping(json.load(f), base=base)


def save_profile(profile: BotProfile, path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as f:
        json.dump(profile_to_dict(profile), f, ensure_ascii=False, indent=2)
        f.write("\n")

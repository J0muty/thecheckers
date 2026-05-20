from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path

from .game_logic import Board, Move, format_move, owner

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MEMORY_PATH = REPO_ROOT / "src/logs/bot_arena/hardcore-learning.json"


def project_path(path: str | Path) -> Path:
    target = Path(path)
    if target.is_absolute():
        return target
    return REPO_ROOT / target


def _mirror_point(point: tuple[int, int]) -> tuple[int, int]:
    row, col = point
    return 7 - row, 7 - col


def _normalize_piece(piece: str, player: str) -> str:
    learner_piece = owner(piece) == player
    if learner_piece:
        return "W" if piece.isupper() else "w"
    return "B" if piece.isupper() else "b"


def board_memory_key(board: Board, player: str) -> str:
    normalized = [["." for _ in range(8)] for _ in range(8)]
    for row in range(8):
        for col in range(8):
            piece = board[row][col]
            if piece is None:
                continue
            target = (row, col) if player == "white" else _mirror_point((row, col))
            normalized[target[0]][target[1]] = _normalize_piece(piece, player)
    rows = ["".join(row) for row in normalized]
    return "v2|" + "/".join(rows)


def move_memory_key(steps: tuple[Move, ...], player: str = "white") -> str:
    normalized_steps = []
    for start, end in steps:
        if player == "black":
            start = _mirror_point(start)
            end = _mirror_point(end)
        normalized_steps.append(format_move(start, end))
    return " ".join(normalized_steps)


def _empty_move_stats() -> dict[str, float | int]:
    return {
        "visits": 0,
        "score_sum": 0.0,
        "wins": 0,
        "draws": 0,
        "losses": 0,
        "last_score": 0.0,
    }


@dataclass
class MoveMemory:
    positions: dict[str, dict[str, dict[str, float | int]]] = field(default_factory=dict)
    total_updates: int = 0
    metadata: dict[str, object] = field(default_factory=dict)

    @classmethod
    def load(cls, path: str | Path = DEFAULT_MEMORY_PATH) -> "MoveMemory":
        target = project_path(path)
        if not target.exists():
            return cls()
        with target.open("r", encoding="utf-8") as f:
            raw = json.load(f)
        if int(raw.get("version", 1)) != 2:
            return cls()
        return cls(
            positions=raw.get("positions", {}),
            total_updates=int(raw.get("total_updates", 0)),
            metadata=raw.get("metadata", {}),
        )

    def save(self, path: str | Path = DEFAULT_MEMORY_PATH) -> None:
        target = project_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8") as f:
            json.dump(
                {
                    "version": 2,
                    "total_updates": self.total_updates,
                    "metadata": self.metadata,
                    "positions": self.positions,
                },
                f,
                ensure_ascii=False,
                indent=2,
            )
            f.write("\n")

    def clone(self) -> "MoveMemory":
        return MoveMemory(
            positions=deepcopy(self.positions),
            total_updates=self.total_updates,
            metadata=deepcopy(self.metadata),
        )

    @property
    def position_count(self) -> int:
        return len(self.positions)

    @property
    def move_count(self) -> int:
        return sum(len(moves) for moves in self.positions.values())

    def apply_draw_pressure(self, draw_score: float = -0.15) -> int:
        if draw_score >= 0:
            return 0

        changed = 0
        for moves in self.positions.values():
            for stats in moves.values():
                visits = int(stats.get("visits", 0))
                draws = int(stats.get("draws", 0))
                wins = int(stats.get("wins", 0))
                losses = int(stats.get("losses", 0))
                if visits <= 0 or draws <= 0 or wins or losses:
                    continue
                target_sum = visits * draw_score
                if float(stats.get("score_sum", 0.0)) > target_sum:
                    stats["score_sum"] = target_sum
                    stats["last_score"] = min(float(stats.get("last_score", 0.0)), draw_score)
                    changed += 1
        return changed

    def stats_for(self, board: Board, player: str, steps: tuple[Move, ...]) -> dict[str, float | int] | None:
        return self.positions.get(board_memory_key(board, player), {}).get(move_memory_key(steps, player))

    def average_score(self, board: Board, player: str, steps: tuple[Move, ...]) -> float | None:
        stats = self.stats_for(board, player, steps)
        if not stats:
            return None
        visits = int(stats.get("visits", 0))
        if visits <= 0:
            return None
        return float(stats.get("score_sum", 0.0)) / visits

    def bias(
        self,
        board: Board,
        player: str,
        steps: tuple[Move, ...],
        *,
        strength: int = 700,
        prior: int = 3,
    ) -> int:
        stats = self.stats_for(board, player, steps)
        if not stats:
            return 0
        visits = int(stats.get("visits", 0))
        if visits <= 0:
            return 0
        average = float(stats.get("score_sum", 0.0)) / visits
        confidence = visits / (visits + prior)
        return round(average * confidence * strength)

    def record(
        self,
        board: Board,
        player: str,
        steps: tuple[Move, ...],
        score: float,
    ) -> None:
        bounded_score = max(-1.0, min(1.0, score))
        position_key = board_memory_key(board, player)
        move_key = move_memory_key(steps, player)
        moves = self.positions.setdefault(position_key, {})
        stats = moves.setdefault(move_key, _empty_move_stats())

        stats["visits"] = int(stats["visits"]) + 1
        stats["score_sum"] = float(stats["score_sum"]) + bounded_score
        stats["last_score"] = bounded_score
        if bounded_score > 0.25:
            stats["wins"] = int(stats["wins"]) + 1
        elif bounded_score < -0.25:
            stats["losses"] = int(stats["losses"]) + 1
        else:
            stats["draws"] = int(stats["draws"]) + 1
        self.total_updates += 1


def outcome_score(status: str, player: str, *, draw_score: float = -0.15) -> float:
    if status == "draw":
        return draw_score
    if status == f"{player}_win":
        return 1.0
    return -1.0

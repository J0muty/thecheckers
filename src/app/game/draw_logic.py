from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from .game_logic import (
    Board,
    apply_move,
    create_initial_board,
    opponent,
    owner,
    parse_move,
    piece_capture_moves,
)

LONG_DIAGONAL = {(row, 7 - row) for row in range(8)}


@dataclass(frozen=True)
class SideMaterial:
    men: int = 0
    kings: int = 0

    @property
    def total(self) -> int:
        return self.men + self.kings


@dataclass(frozen=True)
class RegulationPattern:
    kind: str
    attacker: str
    limit: int


def position_key(board: Board, turn: str) -> str:
    cells = "".join(cell or "." for row in board for cell in row)
    return f"{turn}:{cells}"


def initial_draw_state(board: Board | None = None, turn: str = "white") -> dict[str, Any]:
    current_board = board if board is not None else create_initial_board()
    return {
        "position_counts": {position_key(current_board, turn): 1},
        "king_only_moves": 0,
        "no_progress_moves": 0,
        "regulation": None,
    }


def _piece_positions(board: Board, player: str, *, kings_only: bool = False) -> list[tuple[int, int]]:
    positions: list[tuple[int, int]] = []
    for row in range(8):
        for col in range(8):
            piece = board[row][col]
            if not piece or owner(piece) != player:
                continue
            if kings_only and piece.islower():
                continue
            positions.append((row, col))
    return positions


def _materials(board: Board) -> dict[str, SideMaterial]:
    data = {
        "white": {"men": 0, "kings": 0},
        "black": {"men": 0, "kings": 0},
    }
    for row in board:
        for piece in row:
            if not piece:
                continue
            side = owner(piece)
            if piece.isupper():
                data[side]["kings"] += 1
            else:
                data[side]["men"] += 1
    return {
        side: SideMaterial(men=values["men"], kings=values["kings"])
        for side, values in data.items()
    }


def _no_progress_limit(board: Board) -> int | None:
    materials = _materials(board)
    if materials["white"].kings == 0 or materials["black"].kings == 0:
        return None
    total_pieces = materials["white"].total + materials["black"].total
    if total_pieces in (4, 5):
        return 30
    if total_pieces in (6, 7):
        return 60
    return None


def _regulation_pattern(board: Board) -> RegulationPattern | None:
    materials = _materials(board)
    for attacker in ("white", "black"):
        defender = opponent(attacker)
        attacker_material = materials[attacker]
        defender_material = materials[defender]
        if defender_material.men != 0 or defender_material.kings != 1:
            continue

        defender_king = _piece_positions(board, defender, kings_only=True)[0]
        defender_on_long_diagonal = defender_king in LONG_DIAGONAL

        if defender_on_long_diagonal and attacker_material.total == 3 and (
            attacker_material.kings == 3
            or (attacker_material.kings == 2 and attacker_material.men == 1)
            or (attacker_material.kings == 1 and attacker_material.men == 2)
        ):
            return RegulationPattern("long_diagonal_five", attacker, 5)

        if (
            attacker_material.total == 2
            and (
                attacker_material.kings == 2
                or (attacker_material.kings == 1 and attacker_material.men == 1)
            )
        ) or (attacker_material.total == 1 and attacker_material.kings == 1):
            return RegulationPattern("single_king_five", attacker, 5)

        if attacker_material.kings >= 3:
            return RegulationPattern("three_kings_fifteen", attacker, 15)
    return None


def update_draw_state(
    state: dict[str, Any] | None,
    previous_board: Board,
    new_board: Board,
    moved_player: str,
    next_player: str,
    *,
    moved_piece_was_king: bool,
    was_capture: bool,
    was_promotion: bool,
) -> tuple[dict[str, Any], str | None]:
    draw_state = {
        "position_counts": dict((state or {}).get("position_counts", {})),
        "king_only_moves": int((state or {}).get("king_only_moves", 0)),
        "no_progress_moves": int((state or {}).get("no_progress_moves", 0)),
        "regulation": (state or {}).get("regulation"),
    }

    current_position = position_key(new_board, next_player)
    position_counts = dict(draw_state["position_counts"])
    position_counts[current_position] = position_counts.get(current_position, 0) + 1
    draw_state["position_counts"] = position_counts

    if moved_piece_was_king and not was_capture:
        draw_state["king_only_moves"] += 1
    else:
        draw_state["king_only_moves"] = 0

    no_progress_limit = _no_progress_limit(new_board)
    if no_progress_limit is not None and not was_capture and not was_promotion:
        draw_state["no_progress_moves"] += 1
    else:
        draw_state["no_progress_moves"] = 0

    pattern = _regulation_pattern(new_board)
    previous_regulation = draw_state.get("regulation")
    if pattern is None:
        draw_state["regulation"] = None
    else:
        same_pattern = (
            isinstance(previous_regulation, dict)
            and previous_regulation.get("type") == pattern.kind
            and previous_regulation.get("attacker") == pattern.attacker
        )
        attacker_moves = int(previous_regulation.get("attacker_moves", 0)) if same_pattern else 0
        if moved_player == pattern.attacker:
            attacker_moves += 1
        draw_state["regulation"] = {
            "type": pattern.kind,
            "attacker": pattern.attacker,
            "limit": pattern.limit,
            "attacker_moves": attacker_moves,
        }

    if position_counts[current_position] >= 3:
        return draw_state, "draw"
    if draw_state["king_only_moves"] >= 15:
        return draw_state, "draw"
    if no_progress_limit is not None and draw_state["no_progress_moves"] >= no_progress_limit:
        return draw_state, "draw"
    regulation = draw_state.get("regulation")
    if regulation and int(regulation.get("attacker_moves", 0)) >= int(regulation.get("limit", 0)):
        return draw_state, "draw"
    return draw_state, None


def rebuild_draw_state_from_history(history: Iterable[str]) -> dict[str, Any]:
    board = create_initial_board()
    player = "white"
    state = initial_draw_state(board, player)

    forced_start: tuple[int, int] | None = None
    blocked_positions: tuple[tuple[int, int], ...] = ()
    turn_start_board = board
    turn_piece_was_king = False
    turn_capture = False
    turn_started = False

    for notation in history:
        start, end = parse_move(notation)
        if not turn_started:
            piece = board[start[0]][start[1]]
            turn_start_board = board
            turn_piece_was_king = bool(piece and piece.isupper())
            turn_capture = False
            turn_started = True

        new_board, captured = apply_move(
            board,
            start,
            end,
            player,
            blocked_positions=blocked_positions,
            forced_start=forced_start,
        )

        if captured is not None:
            turn_capture = True
            blocked_positions = blocked_positions + (captured,)
            if piece_capture_moves(new_board, end, player, blocked_positions=blocked_positions):
                board = new_board
                forced_start = end
                continue

        was_promotion = (not turn_piece_was_king) and bool(
            new_board[end[0]][end[1]] and new_board[end[0]][end[1]].isupper()
        )
        next_player = opponent(player)
        state, _ = update_draw_state(
            state,
            turn_start_board,
            new_board,
            player,
            next_player,
            moved_piece_was_king=turn_piece_was_king,
            was_capture=turn_capture,
            was_promotion=was_promotion,
        )
        board = new_board
        player = next_player
        forced_start = None
        blocked_positions = ()
        turn_started = False
        turn_capture = False

    return state

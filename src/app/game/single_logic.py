from __future__ import annotations

import math
import random
import time
import logging
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Tuple

from .game_logic import (
    Board,
    Move,
    TurnSequence,
    DIAGONALS,
    generate_turn_sequences,
    game_status,
    legal_piece_moves,
    opponent,
    owner,
)
from .bot_memory import DEFAULT_MEMORY_PATH, MoveMemory
from .bot_profiles import EvaluationWeights, HARD_WEIGHTS, normalize_difficulty, profile_for_difficulty

WIN_SCORE = 1_000_000
MAN_VALUE = 100
KING_VALUE = 320
DEFAULT_MEMORY_STRENGTH = 240
MAX_ROOT_MEMORY_BONUS = 220
logger = logging.getLogger(__name__)
CENTER_SQUARES = {
    (2, 1), (2, 3), (2, 5), (2, 7),
    (3, 0), (3, 2), (3, 4), (3, 6),
    (4, 1), (4, 3), (4, 5), (4, 7),
    (5, 0), (5, 2), (5, 4), (5, 6),
}


class SearchTimeout(Exception):
    pass


@dataclass
class TTEntry:
    depth: int
    score: int
    flag: str
    best_steps: tuple[Move, ...] | None = None


@dataclass
class SearchContext:
    deadline: float
    weights: EvaluationWeights = HARD_WEIGHTS
    memory: MoveMemory | None = None
    memory_strength: int = DEFAULT_MEMORY_STRENGTH
    cache: dict[tuple, TTEntry] = field(default_factory=dict)
    history: dict[tuple[str, tuple[Move, ...]], int] = field(default_factory=dict)
    nodes: int = 0


@dataclass(frozen=True)
class PieceStats:
    men: int
    kings: int
    center: int
    advancement: int
    back_rank: int
    edge: int
    connected: int
    promotion_ready: int
    activity: int
    king_mobility: int
    trapped: int

    @property
    def total(self) -> int:
        return self.men + self.kings



def legal_moves(
    board: Board,
    pos: Tuple[int, int],
    player: str,
    *,
    blocked_positions=(),
    forced_start=None,
):
    return legal_piece_moves(
        board,
        pos,
        player,
        blocked_positions=blocked_positions,
        forced_start=forced_start,
    )



def board_signature(board: Board, current: str) -> tuple:
    return tuple(tuple(cell or "." for cell in row) for row in board), current



def _check_timeout(ctx: SearchContext) -> None:
    ctx.nodes += 1
    if ctx.nodes & 511 == 0 and time.perf_counter() >= ctx.deadline:
        raise SearchTimeout



def _piece_activity(board: Board, row: int, col: int, piece: str, player: str) -> int:
    activity = 0
    if piece.isupper():
        for dr, dc in DIAGONALS:
            nr, nc = row + dr, col + dc
            while 0 <= nr < 8 and 0 <= nc < 8 and board[nr][nc] is None:
                activity += 1
                nr += dr
                nc += dc
        return activity

    direction = -1 if player == "white" else 1
    for dc in (-1, 1):
        nr, nc = row + direction, col + dc
        if 0 <= nr < 8 and 0 <= nc < 8 and board[nr][nc] is None:
            activity += 1
    return activity


def piece_stats(board: Board, player: str) -> PieceStats:
    men = kings = center = advancement = back_rank = edge = connected = promotion_ready = 0
    activity = king_mobility = trapped = 0
    for row in range(8):
        for col in range(8):
            piece = board[row][col]
            if not piece or owner(piece) != player:
                continue
            piece_activity = _piece_activity(board, row, col, piece, player)
            activity += piece_activity
            if piece_activity == 0:
                trapped += 1
            if piece.isupper():
                kings += 1
                king_mobility += piece_activity
            else:
                men += 1
                advancement += (7 - row) if player == "white" else row
                if (player == "white" and row == 7) or (player == "black" and row == 0):
                    back_rank += 1
                if (player == "white" and row <= 1) or (player == "black" and row >= 6):
                    promotion_ready += 1
            if (row, col) in CENTER_SQUARES:
                center += 1
            if col in (0, 7):
                edge += 1
            for dr, dc in ((-1, -1), (-1, 1), (1, -1), (1, 1)):
                nr, nc = row + dr, col + dc
                if 0 <= nr < 8 and 0 <= nc < 8:
                    neighbor = board[nr][nc]
                    if neighbor and owner(neighbor) == player:
                        connected += 1
                        break
    return PieceStats(
        men=men,
        kings=kings,
        center=center,
        advancement=advancement,
        back_rank=back_rank,
        edge=edge,
        connected=connected,
        promotion_ready=promotion_ready,
        activity=activity,
        king_mobility=king_mobility,
        trapped=trapped,
    )



def threatened_positions(sequences: Iterable[TurnSequence]) -> set[tuple[int, int]]:
    threatened: set[tuple[int, int]] = set()
    for sequence in sequences:
        threatened.update(sequence.captured_positions)
    return threatened



def threatened_material(
    board: Board,
    threatened: set[tuple[int, int]],
    player: str,
    weights: EvaluationWeights = HARD_WEIGHTS,
) -> int:
    total = 0
    for row, col in threatened:
        piece = board[row][col]
        if not piece or owner(piece) != player:
            continue
        total += weights.king_value if piece.isupper() else weights.man_value
    return total



def captured_material(
    board: Board,
    captured: Iterable[tuple[int, int]],
    player: str,
    weights: EvaluationWeights = HARD_WEIGHTS,
) -> int:
    return threatened_material(board, set(captured), player, weights)



def best_capture_length(sequences: Iterable[TurnSequence]) -> int:
    best = 0
    for sequence in sequences:
        if len(sequence.captured_positions) > best:
            best = len(sequence.captured_positions)
    return best



def evaluate_board(
    board: Board,
    player: str,
    weights: EvaluationWeights = HARD_WEIGHTS,
) -> int:
    status = game_status(board)
    if status == f"{player}_win":
        return WIN_SCORE
    if status == f"{opponent(player)}_win":
        return -WIN_SCORE

    enemy = opponent(player)
    my_sequences = generate_turn_sequences(board, player)
    opp_sequences = generate_turn_sequences(board, enemy)

    my_stats = piece_stats(board, player)
    opp_stats = piece_stats(board, enemy)
    total_pieces = my_stats.total + opp_stats.total
    endgame_king_bonus = weights.endgame_king_bonus if total_pieces <= 10 else 0
    king_value = weights.king_value + endgame_king_bonus

    my_material = my_stats.men * weights.man_value + my_stats.kings * king_value
    opp_material = opp_stats.men * weights.man_value + opp_stats.kings * king_value

    my_threatened = threatened_positions(seq for seq in opp_sequences if seq.is_capture)
    opp_threatened = threatened_positions(seq for seq in my_sequences if seq.is_capture)

    my_threatened_material = threatened_material(board, my_threatened, player, weights)
    opp_threatened_material = threatened_material(board, opp_threatened, enemy, weights)

    my_capture_pressure = best_capture_length(my_sequences)
    opp_capture_pressure = best_capture_length(opp_sequences)

    score = 0
    score += my_material - opp_material
    score += (my_stats.center - opp_stats.center) * weights.center
    score += (my_stats.advancement - opp_stats.advancement) * weights.advancement
    score += (my_stats.back_rank - opp_stats.back_rank) * weights.back_rank
    score += (my_stats.connected - opp_stats.connected) * weights.connected
    score += (my_stats.promotion_ready - opp_stats.promotion_ready) * weights.promotion_ready
    score += (len(my_sequences) - len(opp_sequences)) * weights.mobility
    score += (my_capture_pressure - opp_capture_pressure) * weights.capture_pressure
    score += (opp_threatened_material - my_threatened_material) * weights.threatened_material
    score += (my_stats.kings - opp_stats.kings) * weights.king_count
    score += (opp_stats.edge - my_stats.edge) * weights.edge_penalty
    score += (my_stats.activity - opp_stats.activity) * weights.piece_activity
    score += (my_stats.king_mobility - opp_stats.king_mobility) * weights.king_mobility
    score += (opp_stats.trapped - my_stats.trapped) * weights.trapped_piece

    if total_pieces <= 8:
        score += (my_stats.kings - opp_stats.kings) * weights.endgame_king_count
        score += (len(my_sequences) - len(opp_sequences)) * weights.endgame_mobility

    return score



def sequence_promotes(board: Board, sequence: TurnSequence) -> bool:
    start = sequence.steps[0][0]
    end = sequence.steps[-1][1]
    start_piece = board[start[0]][start[1]]
    final_piece = sequence.board[end[0]][end[1]]
    return bool(start_piece and final_piece and start_piece.islower() and final_piece.isupper())



def move_priority(
    board: Board,
    sequence: TurnSequence,
    player: str,
    history: dict[tuple[str, tuple[Move, ...]], int] | None = None,
    tt_steps: tuple[Move, ...] | None = None,
) -> int:
    start = sequence.steps[0][0]
    end = sequence.steps[-1][1]
    moved_piece = sequence.board[end[0]][end[1]]
    advancement = (start[0] - end[0]) if player == "white" else (end[0] - start[0])
    score = 0
    if tt_steps is not None and sequence.steps == tt_steps:
        score += 1_000_000
    score += len(sequence.captured_positions) * 10_000
    if moved_piece and moved_piece.isupper():
        score += 750
    if sequence_promotes(board, sequence):
        score += 1_200
    score += advancement * 45
    if end in CENTER_SQUARES:
        score += 120
    if history is not None:
        score += history.get((player, sequence.steps), 0)
    return score


def root_tactical_bonus(sequence: TurnSequence, weights: EvaluationWeights = HARD_WEIGHTS) -> int:
    if not sequence.is_capture:
        return 0
    capture_value = weights.man_value // 2 + weights.capture_pressure // 2
    return len(sequence.captured_positions) * capture_value


def root_memory_bonus(
    board: Board,
    player: str,
    sequence: TurnSequence,
    memory: MoveMemory | None,
    strength: int,
) -> int:
    if memory is None or strength <= 0:
        return 0
    raw_bonus = memory.bias(board, player, sequence.steps, strength=strength)
    if raw_bonus == 0:
        return 0
    limit = max(60, min(MAX_ROOT_MEMORY_BONUS, strength // 3))
    return max(-limit, min(limit, raw_bonus))


def root_safety_penalty(
    board_after: Board,
    player: str,
    weights: EvaluationWeights = HARD_WEIGHTS,
    *,
    own_capture_value: int = 0,
    own_capture_count: int = 0,
) -> int:
    enemy = opponent(player)
    enemy_sequences = generate_turn_sequences(board_after, enemy)
    if not enemy_sequences:
        return 0

    penalty = 0
    capture_sequences = [seq for seq in enemy_sequences if seq.is_capture]
    if capture_sequences:
        enemy_capture_value = max(
            captured_material(board_after, seq.captured_positions, player, weights)
            for seq in capture_sequences
        )
        enemy_capture_count = max(len(seq.captured_positions) for seq in capture_sequences)
        excess_value = max(0, enemy_capture_value - own_capture_value)
        excess_count = max(0, enemy_capture_count - own_capture_count)
        penalty += excess_value * 3
        penalty += excess_count * (weights.man_value // 2)

    if any(sequence_promotes(board_after, seq) for seq in enemy_sequences):
        penalty += weights.king_value // 2 + weights.promotion_ready * 2

    return penalty



def ordered_turn_sequences(
    board: Board,
    player: str,
    history: dict[tuple[str, tuple[Move, ...]], int] | None = None,
    tt_steps: tuple[Move, ...] | None = None,
) -> list[TurnSequence]:
    sequences = generate_turn_sequences(board, player)
    sequences.sort(
        key=lambda seq: move_priority(board, seq, player, history=history, tt_steps=tt_steps),
        reverse=True,
    )
    return sequences



def quiescence(
    board: Board,
    current: str,
    root_player: str,
    alpha: int,
    beta: int,
    ctx: SearchContext,
    depth: int = 0,
) -> int:
    _check_timeout(ctx)
    stand_pat = evaluate_board(board, root_player, ctx.weights)
    if depth >= 8:
        return stand_pat

    maximizing = current == root_player
    if maximizing:
        if stand_pat >= beta:
            return stand_pat
        alpha = max(alpha, stand_pat)
    else:
        if stand_pat <= alpha:
            return stand_pat
        beta = min(beta, stand_pat)

    capture_sequences = [seq for seq in ordered_turn_sequences(board, current, ctx.history) if seq.is_capture]
    if not capture_sequences:
        return stand_pat

    next_player = opponent(current)
    if maximizing:
        best_score = stand_pat
        for sequence in capture_sequences:
            score = quiescence(sequence.board, next_player, root_player, alpha, beta, ctx, depth + 1)
            if score > best_score:
                best_score = score
            alpha = max(alpha, best_score)
            if alpha >= beta:
                break
        return int(best_score)

    best_score = stand_pat
    for sequence in capture_sequences:
        score = quiescence(sequence.board, next_player, root_player, alpha, beta, ctx, depth + 1)
        if score < best_score:
            best_score = score
        beta = min(beta, best_score)
        if alpha >= beta:
            break
    return int(best_score)



def alpha_beta(
    board: Board,
    current: str,
    root_player: str,
    depth: int,
    alpha: int,
    beta: int,
    ctx: SearchContext,
) -> int:
    _check_timeout(ctx)
    status = game_status(board)
    if status == f"{root_player}_win":
        return WIN_SCORE + depth
    if status == f"{opponent(root_player)}_win":
        return -WIN_SCORE - depth
    if depth <= 0:
        return quiescence(board, current, root_player, alpha, beta, ctx)

    alpha_orig = alpha
    beta_orig = beta
    key = board_signature(board, current)
    entry = ctx.cache.get(key)
    tt_steps = None
    if entry and entry.depth >= depth:
        tt_steps = entry.best_steps
        if entry.flag == "exact":
            return entry.score
        if entry.flag == "lower":
            alpha = max(alpha, entry.score)
        elif entry.flag == "upper":
            beta = min(beta, entry.score)
        if alpha >= beta:
            return entry.score
    elif entry:
        tt_steps = entry.best_steps

    sequences = ordered_turn_sequences(board, current, ctx.history, tt_steps)
    if not sequences:
        return evaluate_board(board, root_player, ctx.weights)

    maximizing = current == root_player
    next_player = opponent(current)
    best_steps: tuple[Move, ...] | None = None

    if maximizing:
        best_score = -math.inf
        for sequence in sequences:
            extension = 1 if depth <= 3 and (sequence.is_capture or sequence_promotes(board, sequence)) else 0
            score = alpha_beta(
                sequence.board,
                next_player,
                root_player,
                depth - 1 + extension,
                alpha,
                beta,
                ctx,
            )
            if score > best_score:
                best_score = score
                best_steps = sequence.steps
            alpha = max(alpha, best_score)
            if alpha >= beta:
                ctx.history[(current, sequence.steps)] = ctx.history.get((current, sequence.steps), 0) + depth * depth
                break
    else:
        best_score = math.inf
        for sequence in sequences:
            extension = 1 if depth <= 3 and (sequence.is_capture or sequence_promotes(board, sequence)) else 0
            score = alpha_beta(
                sequence.board,
                next_player,
                root_player,
                depth - 1 + extension,
                alpha,
                beta,
                ctx,
            )
            if score < best_score:
                best_score = score
                best_steps = sequence.steps
            beta = min(beta, best_score)
            if alpha >= beta:
                ctx.history[(current, sequence.steps)] = ctx.history.get((current, sequence.steps), 0) + depth * depth
                break

    flag = "exact"
    if best_score <= alpha_orig:
        flag = "upper"
    elif best_score >= beta_orig:
        flag = "lower"
    ctx.cache[key] = TTEntry(depth=depth, score=int(best_score), flag=flag, best_steps=best_steps)
    return int(best_score)



def search_root(
    board: Board,
    player: str,
    depth: int,
    sequences: list[TurnSequence],
    ctx: SearchContext,
    preferred_steps: tuple[Move, ...] | None = None,
) -> tuple[TurnSequence, int]:
    tt_entry = ctx.cache.get(board_signature(board, player))
    tt_steps = preferred_steps or (tt_entry.best_steps if tt_entry else None)
    ordered = list(sequences)
    safety_penalties = {
        seq.steps: root_safety_penalty(
            seq.board,
            player,
            ctx.weights,
            own_capture_value=captured_material(
                board,
                seq.captured_positions,
                opponent(player),
                ctx.weights,
            ),
            own_capture_count=len(seq.captured_positions),
        )
        for seq in ordered
    }
    ordered.sort(
        key=lambda seq: (
            move_priority(board, seq, player, history=ctx.history, tt_steps=tt_steps)
            + root_tactical_bonus(seq, ctx.weights)
            + root_memory_bonus(board, player, seq, ctx.memory, ctx.memory_strength)
            - safety_penalties[seq.steps]
        ),
        reverse=True,
    )

    best_sequence = ordered[0]
    best_score = -math.inf
    best_raw_score = -math.inf
    alpha = -WIN_SCORE
    beta = WIN_SCORE
    next_player = opponent(player)

    for sequence in ordered:
        extension = 1 if depth <= 2 and (sequence.is_capture or sequence_promotes(board, sequence)) else 0
        raw_score = alpha_beta(
            sequence.board,
            next_player,
            player,
            depth - 1 + extension,
            alpha,
            beta,
            ctx,
        )
        score = raw_score
        if abs(raw_score) < WIN_SCORE // 2:
            score += root_tactical_bonus(sequence, ctx.weights)
            score += root_memory_bonus(board, player, sequence, ctx.memory, ctx.memory_strength)
            score -= safety_penalties[sequence.steps]
        if score > best_score:
            best_score = score
            best_raw_score = raw_score
            best_sequence = sequence
        if raw_score > alpha:
            alpha = raw_score

    ctx.cache[board_signature(board, player)] = TTEntry(
        depth=depth,
        score=int(best_raw_score),
        flag="exact",
        best_steps=best_sequence.steps,
    )
    return best_sequence, int(best_score)



def search_best_turn(
    board: Board,
    player: str,
    sequences: list[TurnSequence],
    *,
    max_depth: int,
    time_limit: float,
    weights: EvaluationWeights = HARD_WEIGHTS,
    memory: MoveMemory | None = None,
    memory_strength: int = DEFAULT_MEMORY_STRENGTH,
) -> TurnSequence:
    if len(sequences) == 1:
        return sequences[0]

    ctx = SearchContext(
        deadline=time.perf_counter() + time_limit,
        weights=weights,
        memory=memory,
        memory_strength=memory_strength,
    )
    best_sequence = sequences[0]
    preferred_steps = best_sequence.steps

    for depth in range(1, max_depth + 1):
        try:
            candidate, _ = search_root(
                board,
                player,
                depth,
                sequences,
                ctx,
                preferred_steps=preferred_steps,
            )
        except SearchTimeout:
            break
        best_sequence = candidate
        preferred_steps = candidate.steps

    return best_sequence



def select_easy_turn(sequences: list[TurnSequence]) -> TurnSequence:
    capture_sequences = [seq for seq in sequences if seq.is_capture]
    pool = capture_sequences or sequences
    return random.choice(pool)



def select_medium_turn(
    board: Board,
    player: str,
    sequences: list[TurnSequence],
    *,
    weights: EvaluationWeights = HARD_WEIGHTS,
    time_limit: float = 0.2,
) -> TurnSequence:
    ctx = SearchContext(deadline=time.perf_counter() + time_limit, weights=weights)
    scored: list[tuple[int, TurnSequence]] = []
    for sequence in sequences:
        try:
            score = alpha_beta(
                sequence.board,
                opponent(player),
                player,
                2,
                -WIN_SCORE,
                WIN_SCORE,
                ctx,
            )
        except SearchTimeout:
            if scored:
                break
            score = evaluate_board(sequence.board, player, weights)
        score += len(sequence.captured_positions) * 14
        scored.append((score, sequence))
    scored.sort(key=lambda item: item[0], reverse=True)
    top_band = scored[: min(2, len(scored))]
    if len(top_band) == 1:
        return top_band[0][1]
    return random.choice([sequence for _, sequence in top_band])



def select_hard_turn(
    board: Board,
    player: str,
    sequences: list[TurnSequence],
    *,
    weights: EvaluationWeights = HARD_WEIGHTS,
    max_depth: int | None = None,
    time_limit: float | None = None,
    memory: MoveMemory | None = None,
    memory_strength: int = DEFAULT_MEMORY_STRENGTH,
) -> TurnSequence:
    piece_count = sum(1 for row in board for piece in row if piece)
    if max_depth is None or time_limit is None:
        if piece_count > 18:
            default_depth = 12
            default_time = 6.0
        elif piece_count > 12:
            default_depth = 13
            default_time = 8.0
        elif piece_count > 8:
            default_depth = 14
            default_time = 10.0
        else:
            default_depth = 16
            default_time = 12.0
        max_depth = default_depth if max_depth is None else max_depth
        time_limit = default_time if time_limit is None else time_limit
    return search_best_turn(
        board,
        player,
        sequences,
        max_depth=max_depth,
        time_limit=time_limit,
        weights=weights,
        memory=memory,
        memory_strength=memory_strength,
    )



def choose_turn(
    board: Board,
    player: str,
    difficulty: str,
    *,
    max_depth: int | None = None,
    time_limit: float | None = None,
    weights: EvaluationWeights | None = None,
    memory: MoveMemory | None = None,
    memory_strength: int = DEFAULT_MEMORY_STRENGTH,
    use_default_memory: bool = True,
) -> TurnSequence | None:
    profile = profile_for_difficulty(difficulty)
    normalized_difficulty = normalize_difficulty(difficulty)
    active_weights = weights or profile.weights
    active_memory = memory
    if active_memory is None and use_default_memory and normalized_difficulty == "hardcore":
        active_memory = MoveMemory.load(DEFAULT_MEMORY_PATH)
    sequences = ordered_turn_sequences(board, player)
    if not sequences:
        return None
    if difficulty == "easy":
        return select_easy_turn(sequences)
    if difficulty == "medium":
        return select_medium_turn(
            board,
            player,
            sequences,
            weights=active_weights,
            time_limit=time_limit or 0.2,
        )
    return select_hard_turn(
        board,
        player,
        sequences,
        weights=active_weights,
        max_depth=max_depth,
        time_limit=time_limit,
        memory=active_memory,
        memory_strength=memory_strength,
    )


async def bot_turn(
    board: Board,
    player: str,
    difficulty: str = "easy",
) -> tuple[Board, list[tuple[int, int]], list[tuple[int, int]]]:
    try:
        sequence = choose_turn(board, player, difficulty)
    except SearchTimeout:
        logger.warning("Bot search timed out for %s difficulty=%s, falling back to best ordered move", player, difficulty)
        fallback_sequences = ordered_turn_sequences(board, player)
        sequence = fallback_sequences[0] if fallback_sequences else None
    if sequence is None:
        return board, [], []
    starts = [start for start, _ in sequence.steps]
    ends = [end for _, end in sequence.steps]
    return sequence.board, starts, ends

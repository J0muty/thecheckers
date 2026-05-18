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
    generate_turn_sequences,
    game_status,
    legal_piece_moves,
    opponent,
    owner,
)

WIN_SCORE = 1_000_000
MAN_VALUE = 100
KING_VALUE = 320
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



def piece_stats(board: Board, player: str) -> PieceStats:
    men = kings = center = advancement = back_rank = edge = connected = promotion_ready = 0
    for row in range(8):
        for col in range(8):
            piece = board[row][col]
            if not piece or owner(piece) != player:
                continue
            if piece.isupper():
                kings += 1
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
    )



def threatened_positions(sequences: Iterable[TurnSequence]) -> set[tuple[int, int]]:
    threatened: set[tuple[int, int]] = set()
    for sequence in sequences:
        threatened.update(sequence.captured_positions)
    return threatened



def threatened_material(board: Board, threatened: set[tuple[int, int]], player: str) -> int:
    total = 0
    for row, col in threatened:
        piece = board[row][col]
        if not piece or owner(piece) != player:
            continue
        total += KING_VALUE if piece.isupper() else MAN_VALUE
    return total



def best_capture_length(sequences: Iterable[TurnSequence]) -> int:
    best = 0
    for sequence in sequences:
        if len(sequence.captured_positions) > best:
            best = len(sequence.captured_positions)
    return best



def evaluate_board(board: Board, player: str) -> int:
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
    endgame_king_bonus = 35 if total_pieces <= 10 else 0
    king_value = KING_VALUE + endgame_king_bonus

    my_material = my_stats.men * MAN_VALUE + my_stats.kings * king_value
    opp_material = opp_stats.men * MAN_VALUE + opp_stats.kings * king_value

    my_threatened = threatened_positions(seq for seq in opp_sequences if seq.is_capture)
    opp_threatened = threatened_positions(seq for seq in my_sequences if seq.is_capture)

    my_threatened_material = threatened_material(board, my_threatened, player)
    opp_threatened_material = threatened_material(board, opp_threatened, enemy)

    my_capture_pressure = best_capture_length(my_sequences)
    opp_capture_pressure = best_capture_length(opp_sequences)

    score = 0
    score += my_material - opp_material
    score += (my_stats.center - opp_stats.center) * 8
    score += (my_stats.advancement - opp_stats.advancement) * 7
    score += (my_stats.back_rank - opp_stats.back_rank) * 5
    score += (my_stats.connected - opp_stats.connected) * 6
    score += (my_stats.promotion_ready - opp_stats.promotion_ready) * 18
    score += (len(my_sequences) - len(opp_sequences)) * 5
    score += (my_capture_pressure - opp_capture_pressure) * 28
    score += opp_threatened_material - my_threatened_material
    score += (my_stats.kings - opp_stats.kings) * 32
    score += (opp_stats.edge - my_stats.edge) * 3

    if total_pieces <= 8:
        score += (my_stats.kings - opp_stats.kings) * 24
        score += (len(my_sequences) - len(opp_sequences)) * 3

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
    stand_pat = evaluate_board(board, root_player)
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
        return evaluate_board(board, root_player)

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
    ordered.sort(
        key=lambda seq: move_priority(board, seq, player, history=ctx.history, tt_steps=tt_steps),
        reverse=True,
    )

    best_sequence = ordered[0]
    best_score = -math.inf
    alpha = -WIN_SCORE
    beta = WIN_SCORE
    next_player = opponent(player)

    for sequence in ordered:
        extension = 1 if depth <= 2 and (sequence.is_capture or sequence_promotes(board, sequence)) else 0
        score = alpha_beta(
            sequence.board,
            next_player,
            player,
            depth - 1 + extension,
            alpha,
            beta,
            ctx,
        )
        if score > best_score:
            best_score = score
            best_sequence = sequence
        if score > alpha:
            alpha = score

    ctx.cache[board_signature(board, player)] = TTEntry(
        depth=depth,
        score=int(best_score),
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
) -> TurnSequence:
    if len(sequences) == 1:
        return sequences[0]

    ctx = SearchContext(deadline=time.perf_counter() + time_limit)
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



def select_medium_turn(board: Board, player: str, sequences: list[TurnSequence]) -> TurnSequence:
    ctx = SearchContext(deadline=time.perf_counter() + 0.2)
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
            score = evaluate_board(sequence.board, player)
        score += len(sequence.captured_positions) * 14
        scored.append((score, sequence))
    scored.sort(key=lambda item: item[0], reverse=True)
    top_band = scored[: min(2, len(scored))]
    if len(top_band) == 1:
        return top_band[0][1]
    return random.choice([sequence for _, sequence in top_band])



def select_hard_turn(board: Board, player: str, sequences: list[TurnSequence]) -> TurnSequence:
    piece_count = sum(1 for row in board for piece in row if piece)
    if piece_count > 18:
        max_depth = 12
        time_limit = 6.0
    elif piece_count > 12:
        max_depth = 13
        time_limit = 8.0
    elif piece_count > 8:
        max_depth = 14
        time_limit = 10.0
    else:
        max_depth = 16
        time_limit = 12.0
    return search_best_turn(board, player, sequences, max_depth=max_depth, time_limit=time_limit)



def choose_turn(board: Board, player: str, difficulty: str) -> TurnSequence | None:
    sequences = ordered_turn_sequences(board, player)
    if not sequences:
        return None
    if difficulty == "easy":
        return select_easy_turn(sequences)
    if difficulty == "medium":
        return select_medium_turn(board, player, sequences)
    return select_hard_turn(board, player, sequences)


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

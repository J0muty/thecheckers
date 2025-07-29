import random
import asyncio
from typing import List, Tuple
import math

from .game_logic import (
    validate_move,
    piece_capture_moves,
    man_moves,
    king_moves,
    any_capture,
    owner,
    get_piece,
    Board,
)

def legal_moves(board: Board, pos: Tuple[int, int], player: str) -> List[Tuple[int, int]]:
    r, c = pos
    piece = get_piece(board, pos)
    if not piece or owner(piece) != player:
        return []
    if any_capture(board, player):
        return piece_capture_moves(board, pos, player)
    moves_f = man_moves if piece.islower() else king_moves
    return moves_f(board, pos, player)

async def available_moves(board: Board, player: str) -> List[Tuple[Tuple[int, int], Tuple[int, int]]]:
    moves: List[Tuple[Tuple[int, int], Tuple[int, int]]] = []
    forced = any_capture(board, player)
    for r in range(8):
        for c in range(8):
            piece = get_piece(board, (r, c))
            if not piece or owner(piece) != player:
                continue
            if forced:
                caps = piece_capture_moves(board, (r, c), player)
                for dest in caps:
                    moves.append(((r, c), dest))
            else:
                opts = man_moves(board, (r, c), player) if piece.islower() else king_moves(board, (r, c), player)
                for dest in opts:
                    moves.append(((r, c), dest))
    return moves

def evaluate_board(board: Board, player: str) -> int:
    score = 0
    for row in board:
        for p in row:
            if p is None:
                continue
            val = 3 if p.isupper() else 1
            if owner(p) == player:
                score += val
            else:
                score -= val
    return score

async def random_bot_move(board: Board, player: str) -> Tuple[Board, Tuple[int, int], Tuple[int, int]]:
    moves = await available_moves(board, player)
    if not moves:
        return board, (-1, -1), (-1, -1)
    start, end = random.choice(moves)
    new_board = validate_move(board, start, end, player)
    return new_board, start, end

async def heuristic_bot_move(board: Board, player: str) -> Tuple[Board, Tuple[int, int], Tuple[int, int]]:
    best_score = -math.inf
    best_board = board
    best_move = (-1, -1), (-1, -1)
    moves = await available_moves(board, player)
    if not moves:
        return board, best_move[0], best_move[1]
    for start, end in moves:
        nb = validate_move(board, start, end, player)
        s = evaluate_board(nb, player)
        if s > best_score:
            best_score = s
            best_board = nb
            best_move = (start, end)
    return best_board, best_move[0], best_move[1]

async def minimax(board: Board, current: str, me: str, depth: int, alpha: float, beta: float) -> int:
    if depth == 0:
        return evaluate_board(board, me)
    moves = await available_moves(board, current)
    if not moves:
        return evaluate_board(board, me)
    if current == me:
        value = -math.inf
        for start, end in moves:
            nb = validate_move(board, start, end, current)
            score = await minimax(nb, 'white' if current == 'black' else 'black', me, depth - 1, alpha, beta)
            value = max(value, score)
            alpha = max(alpha, value)
            if beta <= alpha:
                break
        return value
    value = math.inf
    for start, end in moves:
        nb = validate_move(board, start, end, current)
        score = await minimax(nb, 'white' if current == 'black' else 'black', me, depth - 1, alpha, beta)
        value = min(value, score)
        beta = min(beta, value)
        if beta <= alpha:
            break
    return value

async def minimax_bot_move(board: Board, player: str, depth: int = 4) -> Tuple[Board, Tuple[int, int], Tuple[int, int]]:
    best_score = -math.inf
    best_board = board
    best_move = (-1, -1), (-1, -1)
    moves = await available_moves(board, player)
    if not moves:
        return board, best_move[0], best_move[1]
    for start, end in moves:
        nb = validate_move(board, start, end, player)
        score = await minimax(nb, 'white' if player == 'black' else 'black', player, depth - 1, -math.inf, math.inf)
        if score > best_score:
            best_score = score
            best_board = nb
            best_move = (start, end)
    return best_board, best_move[0], best_move[1]

async def bot_turn(
    board: Board, player: str, difficulty: str = "easy"
) -> Tuple[Board, List[Tuple[int, int]], List[Tuple[int, int]], List[Board]]:
    if difficulty == "easy":
        board, start, end = await random_bot_move(board, player)
    elif difficulty == "medium":
        board, start, end = await heuristic_bot_move(board, player)
    else:
        board, start, end = await minimax_bot_move(board, player)
    if start == (-1, -1):
        return board, [], [], []
    starts = [start]
    ends = [end]
    boards = [board]

    is_capture = abs(end[0] - start[0]) > 1 or abs(end[1] - start[1]) > 1
    while is_capture:
        caps = piece_capture_moves(board, end, player)
        if not caps:
            break
        if difficulty == "easy":
            dest = random.choice(caps)
            nb = validate_move(board, end, dest, player)
        elif difficulty == "medium":
            best_score = -math.inf
            dest = caps[0]
            nb = board
            for d in caps:
                cb = validate_move(board, end, d, player)
                sc = evaluate_board(cb, player)
                if sc > best_score:
                    best_score = sc
                    dest = d
                    nb = cb
        else:
            best_score = -math.inf
            dest = caps[0]
            nb = board
            for d in caps:
                cb = validate_move(board, end, d, player)
                sc = await minimax(
                    cb,
                    'white' if player == 'black' else 'black',
                    player,
                    3,
                    -math.inf,
                    math.inf,
                )
                if sc > best_score:
                    best_score = sc
                    dest = d
                    nb = cb
        board = nb
        start = end
        end = dest
        starts.append(start)
        ends.append(end)
        boards.append(board)
        is_capture = abs(end[0] - start[0]) > 1 or abs(end[1] - start[1]) > 1

    return board, starts, ends, boards

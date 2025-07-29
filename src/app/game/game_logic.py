from __future__ import annotations
import logging
import time
import os
import asyncio
import functools
from copy import deepcopy
from typing import List, Optional, Tuple

os.makedirs("src/logs", exist_ok=True)
logger = logging.getLogger("game_logic")
logger.setLevel(logging.INFO)
fh = logging.FileHandler("src/logs/game_logic.log", encoding="utf-8")
fmt = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
fh.setFormatter(fmt)
logger.addHandler(fh)

def log_time(func):
    if asyncio.iscoroutinefunction(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            start = time.time()
            result = await func(*args, **kwargs)
            duration = (time.time() - start) * 1000
            logger.info(f"Функция {func.__name__} выполнилась за {duration:.2f} мс")
            return result
        return wrapper
    else:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start = time.time()
            result = func(*args, **kwargs)
            duration = (time.time() - start) * 1000
            logger.info(f"Функция {func.__name__} выполнилась за {duration:.2f} мс")
            return result
        return wrapper

Board = List[List[Optional[str]]]

@log_time
def create_initial_board() -> Board:
    board: Board = [[None for _ in range(8)] for _ in range(8)]
    for row in range(3):
        for col in range(8):
            if (row + col) % 2 == 1:
                board[row][col] = 'b'
    for row in range(5, 8):
        for col in range(8):
            if (row + col) % 2 == 1:
                board[row][col] = 'w'
    return board

def within_bounds(pos: Tuple[int, int]) -> bool:
    r, c = pos
    return 0 <= r < 8 and 0 <= c < 8

def get_piece(board: Board, pos: Tuple[int, int]) -> Optional[str]:
    r, c = pos
    return board[r][c]

def is_empty(board: Board, pos: Tuple[int, int]) -> bool:
    return get_piece(board, pos) is None

def owner(piece: str) -> str:
    return 'white' if piece.lower() == 'w' else 'black'

def is_opponent(piece: str, player: str) -> bool:
    if not piece:
        return False
    return (piece.lower() == 'w' and player == 'black') or (piece.lower() == 'b' and player == 'white')

def sign(n: int) -> int:
    return (n > 0) - (n < 0)

@log_time
def man_moves(board: Board, pos: Tuple[int, int], player: str) -> List[Tuple[int, int]]:
    r, c = pos
    caps: List[Tuple[int, int]] = []
    for dr, dc in [(-2, -2), (-2, 2), (2, -2), (2, 2)]:
        dest_r, dest_c = r + dr, c + dc
        mid_r, mid_c = r + dr // 2, c + dc // 2
        if 0 <= dest_r < 8 and 0 <= dest_c < 8:
            if board[dest_r][dest_c] is None:
                mid_piece = board[mid_r][mid_c] if 0 <= mid_r < 8 and 0 <= mid_c < 8 else None
                if mid_piece and is_opponent(mid_piece, player):
                    caps.append((dest_r, dest_c))
    if caps:
        return caps
    moves: List[Tuple[int, int]] = []
    direction = -1 if player == 'white' else 1
    for dc in (-1, 1):
        dest_r, dest_c = r + direction, c + dc
        if 0 <= dest_r < 8 and 0 <= dest_c < 8:
            if board[dest_r][dest_c] is None:
                moves.append((dest_r, dest_c))
    return moves

@log_time
def king_moves(board: Board, pos: Tuple[int, int], player: str) -> List[Tuple[int, int]]:
    r, c = pos
    caps: List[Tuple[int, int]] = []
    for dr_sign, dc_sign in [(-1, -1), (-1, 1), (1, -1), (1, 1)]:
        i, j = r + dr_sign, c + dc_sign
        while 0 <= i < 8 and 0 <= j < 8 and board[i][j] is None:
            i += dr_sign
            j += dc_sign
        if 0 <= i < 8 and 0 <= j < 8:
            piece_at = board[i][j]
            if piece_at and is_opponent(piece_at, player):
                i2, j2 = i + dr_sign, j + dc_sign
                while 0 <= i2 < 8 and 0 <= j2 < 8:
                    if board[i2][j2] is None:
                        caps.append((i2, j2))
                    else:
                        break
                    i2 += dr_sign
                    j2 += dc_sign
    if caps:
        return caps
    moves: List[Tuple[int, int]] = []
    for dr_sign, dc_sign in [(-1, -1), (-1, 1), (1, -1), (1, 1)]:
        i, j = r + dr_sign, c + dc_sign
        while 0 <= i < 8 and 0 <= j < 8 and board[i][j] is None:
            moves.append((i, j))
            i += dr_sign
            j += dc_sign
    return moves

def piece_capture_moves(board: Board, pos: Tuple[int, int], player: str) -> List[Tuple[int, int]]:
    p = board[pos[0]][pos[1]]
    if not p or owner(p) != player:
        return []
    caps: List[Tuple[int, int]] = []
    if p.islower():
        r, c = pos
        for dr, dc in [(-2, -2), (-2, 2), (2, -2), (2, 2)]:
            dest_r, dest_c = r + dr, c + dc
            mid_r, mid_c = r + dr // 2, c + dc // 2
            if 0 <= dest_r < 8 and 0 <= dest_c < 8:
                if board[dest_r][dest_c] is None:
                    mid_piece = board[mid_r][mid_c] if 0 <= mid_r < 8 and 0 <= mid_c < 8 else None
                    if mid_piece and is_opponent(mid_piece, player):
                        caps.append((dest_r, dest_c))
    else:
        r, c = pos
        for dr_sign, dc_sign in [(-1, -1), (-1, 1), (1, -1), (1, 1)]:
            i, j = r + dr_sign, c + dc_sign
            while 0 <= i < 8 and 0 <= j < 8 and board[i][j] is None:
                i += dr_sign
                j += dc_sign
            if 0 <= i < 8 and 0 <= j < 8:
                piece_at = board[i][j]
                if piece_at and is_opponent(piece_at, player):
                    i2, j2 = i + dr_sign, j + dc_sign
                    while 0 <= i2 < 8 and 0 <= j2 < 8:
                        if board[i2][j2] is None:
                            caps.append((i2, j2))
                        else:
                            break
                        i2 += dr_sign
                        j2 += dc_sign
    return caps

@log_time
def any_capture(board: Board, player: str) -> bool:
    for rr in range(8):
        for cc in range(8):
            if piece_capture_moves(board, (rr, cc), player):
                return True
    return False

@log_time
def validate_move(board: Board, start: Tuple[int, int], end: Tuple[int, int], player: str) -> Board:
    sr, sc = start
    er, ec = end
    if not (0 <= sr < 8 and 0 <= sc < 8 and 0 <= er < 8 and 0 <= ec < 8):
        raise ValueError('Позиция вне доски')
    piece = board[sr][sc]
    if not piece or ((player == 'white' and piece.lower() != 'w') or (player == 'black' and piece.lower() != 'b')) or board[er][ec] is not None:
        raise ValueError('Неверный ход')
    forced = any_capture(board, player)
    captures = piece_capture_moves(board, start, player)
    if forced and not captures:
        raise ValueError('Обязательное взятие')
    possible = captures if captures else (man_moves(board, start, player) if piece.islower() else king_moves(board, start, player))
    if end not in possible:
        raise ValueError('Неверный ход')
    new_board = [row[:] for row in board]
    new_board[sr][sc] = None
    new_board[er][ec] = piece
    if captures and end in captures:
        dr = sign(er - sr)
        dc = sign(ec - sc)
        i, j = sr + dr, sc + dc
        while (i, j) != (er, ec):
            mid_piece = new_board[i][j]
            if mid_piece and is_opponent(mid_piece, player):
                new_board[i][j] = None
                break
            i += dr
            j += dc
    if piece == 'w' and er == 0:
        new_board[er][ec] = 'W'
    if piece == 'b' and er == 7:
        new_board[er][ec] = 'B'
    return new_board

@log_time
def game_status(board: Board) -> Optional[str]:
    white_has_pieces = False
    black_has_pieces = False
    white_can_move = False
    black_can_move = False
    only_kings = True
    for r in range(8):
        for c in range(8):
            p = board[r][c]
            if not p:
                continue
            if p.islower():
                only_kings = False
            if p.lower() == 'w':
                white_has_pieces = True
                moves = man_moves(board, (r, c), 'white') if p.islower() else king_moves(board, (r, c), 'white')
                if moves:
                    white_can_move = True
            else:
                black_has_pieces = True
                moves = man_moves(board, (r, c), 'black') if p.islower() else king_moves(board, (r, c), 'black')
                if moves:
                    black_can_move = True
    if not black_has_pieces or not black_can_move:
        return "white_win"
    if not white_has_pieces or not white_can_move:
        return "black_win"
    if only_kings and not any_capture(board, 'white') and not any_capture(board, 'black'):
        return "draw"
    return None

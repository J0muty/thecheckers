from __future__ import annotations
from copy import deepcopy
from typing import List, Optional, Tuple
import logging

Board = List[List[Optional[str]]]

logger = logging.getLogger(__name__)


async def create_initial_board() -> Board:
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
    return owner(piece) != player


def sign(n: int) -> int:
    return (n > 0) - (n < 0)


def man_moves(
    board: Board, pos: Tuple[int, int], player: str
) -> List[Tuple[int, int]]:
    r, c = pos
    caps: List[Tuple[int, int]] = []
    for dr, dc in [(-2, -2), (-2, 2), (2, -2), (2, 2)]:
        mid = (r + dr // 2, c + dc // 2)
        dest = (r + dr, c + dc)
        if (
            within_bounds(dest)
            and is_empty(board, dest)
            and get_piece(board, mid)
            and is_opponent(get_piece(board, mid), player)
        ):
            caps.append(dest)
    if caps:
        return caps

    moves: List[Tuple[int, int]] = []
    direction = -1 if player == 'white' else 1
    for dc in (-1, 1):
        dest = (r + direction, c + dc)
        if within_bounds(dest) and is_empty(board, dest):
            moves.append(dest)
    return moves


def king_moves(
    board: Board, pos: Tuple[int, int], player: str
) -> List[Tuple[int, int]]:
    r, c = pos
    caps: List[Tuple[int, int]] = []
    for dr_sign, dc_sign in [(-1, -1), (-1, 1), (1, -1), (1, 1)]:
        i, j = r + dr_sign, c + dc_sign
        while within_bounds((i, j)) and is_empty(board, (i, j)):
            i += dr_sign
            j += dc_sign
        if (
            within_bounds((i, j))
            and get_piece(board, (i, j))
            and is_opponent(get_piece(board, (i, j)), player)
        ):
            i2, j2 = i + dr_sign, j + dc_sign
            while within_bounds((i2, j2)):
                if is_empty(board, (i2, j2)):
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
        while within_bounds((i, j)) and is_empty(board, (i, j)):
            moves.append((i, j))
            i += dr_sign
            j += dc_sign
    return moves


def piece_capture_moves(
    board: Board, pos: Tuple[int, int], player: str
) -> List[Tuple[int, int]]:
    p = get_piece(board, pos)
    if not p or owner(p) != player:
        return []
    caps: List[Tuple[int, int]] = []
    if p.islower():
        r, c = pos
        for dr, dc in [(-2, -2), (-2, 2), (2, -2), (2, 2)]:
            mid = (r + dr // 2, c + dc // 2)
            dest = (r + dr, c + dc)
            if (
                within_bounds(dest)
                and is_empty(board, dest)
                and get_piece(board, mid)
                and is_opponent(get_piece(board, mid), player)
            ):
                caps.append(dest)
    else:
        r, c = pos
        for dr_sign, dc_sign in [(-1, -1), (-1, 1), (1, -1), (1, 1)]:
            i, j = r + dr_sign, c + dc_sign
            while within_bounds((i, j)) and is_empty(board, (i, j)):
                i += dr_sign
                j += dc_sign
            if (
                within_bounds((i, j))
                and get_piece(board, (i, j))
                and is_opponent(get_piece(board, (i, j)), player)
            ):
                i2, j2 = i + dr_sign, j + dc_sign
                while within_bounds((i2, j2)):
                    if is_empty(board, (i2, j2)):
                        caps.append((i2, j2))
                    else:
                        break
                    i2 += dr_sign
                    j2 += dc_sign
    return caps


def any_capture(board: Board, player: str) -> bool:
    for rr in range(8):
        for cc in range(8):
            if piece_capture_moves(board, (rr, cc), player):
                return True
    return False


async def validate_move(
    board: Board, start: Tuple[int, int], end: Tuple[int, int], player: str
) -> Board:
    if not within_bounds(start) or not within_bounds(end):
        logger.error(
            "Move out of bounds: %s -> %s by %s", start, end, player
        )
        raise ValueError('Позиция вне доски')
    piece = get_piece(board, start)
    if not piece or owner(piece) != player or not is_empty(board, end):
        logger.error(
            "Invalid move: %s -> %s by %s", start, end, player
        )
        raise ValueError('Неверный ход')
    forced = any_capture(board, player)
    captures = piece_capture_moves(board, start, player)
    if forced and not captures:
        logger.error(
            "Forced capture missed: %s -> %s by %s", start, end, player
        )
        raise ValueError('Обязательное взятие')
    possible = captures if captures else (
        man_moves(board, start, player)
        if piece.islower()
        else king_moves(board, start, player)
    )
    if end not in possible:
        logger.error(
            "Move not allowed: %s -> %s by %s", start, end, player
        )
        raise ValueError('Неверный ход')
    new_board = deepcopy(board)
    new_board[start[0]][start[1]] = None
    new_board[end[0]][end[1]] = piece
    if captures and end in captures:
        dr = sign(end[0] - start[0])
        dc = sign(end[1] - start[1])
        i, j = start[0] + dr, start[1] + dc
        while (i, j) != end:
            if get_piece(new_board, (i, j)) and is_opponent(get_piece(new_board, (i, j)), player):
                new_board[i][j] = None
                break
            i += dr
            j += dc
    if piece == 'w' and end[0] == 0:
        new_board[end[0]][end[1]] = 'W'
    if piece == 'b' and end[0] == 7:
        new_board[end[0]][end[1]] = 'B'
    return new_board


def game_status(board: Board) -> Optional[str]:
    white_has_pieces = False
    black_has_pieces = False
    white_can_move = False
    black_can_move = False
    for r in range(8):
        for c in range(8):
            p = board[r][c]
            if not p:
                continue
            pl = 'white' if p.lower() == 'w' else 'black'
            if pl == 'white':
                white_has_pieces = True
            else:
                black_has_pieces = True
            moves = (
                man_moves(board, (r, c), pl)
                if p.islower()
                else king_moves(board, (r, c), pl)
            )
            caps = piece_capture_moves(board, (r, c), pl)
            if moves or caps:
                if pl == 'white':
                    white_can_move = True
                else:
                    black_can_move = True
    if not black_has_pieces or not black_can_move:
        return "white_win"
    if not white_has_pieces or not white_can_move:
        return "black_win"
    only_kings = all(
        p is None or p.isupper()
        for row in board for p in row
    )
    if only_kings and not any_capture(board, 'white') and not any_capture(board, 'black'):
        return "draw"
    return None

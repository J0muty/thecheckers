from __future__ import annotations

import asyncio
import functools
import logging
import os
import time
from dataclasses import dataclass
from typing import Collection, Iterable, List, Optional, Sequence, Tuple

os.makedirs("src/logs", exist_ok=True)
logger = logging.getLogger("game_logic")
logger.setLevel(logging.INFO)
if not logger.handlers:
    fh = logging.FileHandler("src/logs/game_logic.log", encoding="utf-8")
    fmt = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

PROFILE_GAME_LOGIC = os.getenv("CHECKERS_PROFILE_GAME_LOGIC") == "1"
SLOW_LOG_THRESHOLD_MS = float(os.getenv("CHECKERS_GAME_LOG_SLOW_MS", "5"))
DIAGONALS: tuple[tuple[int, int], ...] = ((-1, -1), (-1, 1), (1, -1), (1, 1))

Board = List[List[Optional[str]]]
Point = Tuple[int, int]
Move = Tuple[Point, Point]


@dataclass(frozen=True)
class TurnSequence:
    steps: tuple[Move, ...]
    board: Board
    captured_positions: tuple[Point, ...] = ()

    @property
    def is_capture(self) -> bool:
        return bool(self.captured_positions)

    @property
    def start(self) -> Point:
        return self.steps[0][0]

    @property
    def end(self) -> Point:
        return self.steps[-1][1]


def log_time(func):
    if not PROFILE_GAME_LOGIC:
        return func

    if asyncio.iscoroutinefunction(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            start = time.perf_counter()
            result = await func(*args, **kwargs)
            duration = (time.perf_counter() - start) * 1000
            if duration >= SLOW_LOG_THRESHOLD_MS:
                logger.info("Функция %s выполнилась за %.2f мс", func.__name__, duration)
            return result

        return wrapper

    @functools.wraps(func)
    def sync_wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = func(*args, **kwargs)
        duration = (time.perf_counter() - start) * 1000
        if duration >= SLOW_LOG_THRESHOLD_MS:
            logger.info("Функция %s выполнилась за %.2f мс", func.__name__, duration)
        return result

    return sync_wrapper


@log_time
def create_initial_board() -> Board:
    board: Board = [[None for _ in range(8)] for _ in range(8)]
    for row in range(3):
        for col in range(8):
            if (row + col) % 2 == 1:
                board[row][col] = "b"
    for row in range(5, 8):
        for col in range(8):
            if (row + col) % 2 == 1:
                board[row][col] = "w"
    return board


def within_bounds(pos: Point) -> bool:
    r, c = pos
    return 0 <= r < 8 and 0 <= c < 8


def get_piece(board: Board, pos: Point) -> Optional[str]:
    r, c = pos
    return board[r][c]


def is_empty(board: Board, pos: Point) -> bool:
    return get_piece(board, pos) is None


def owner(piece: str) -> str:
    return "white" if piece.lower() == "w" else "black"


def opponent(player: str) -> str:
    return "black" if player == "white" else "white"


def is_opponent(piece: str | None, player: str) -> bool:
    if not piece:
        return False
    return owner(piece) != player


def sign(n: int) -> int:
    return (n > 0) - (n < 0)


def normalize_blocked_positions(blocked_positions: Collection[Point] | None = None) -> set[Point]:
    return set(blocked_positions or ())


def format_move(start: Point, end: Point) -> str:
    return f"{chr(start[1] + 65)}{8 - start[0]}->{chr(end[1] + 65)}{8 - end[0]}"


def parse_move(move: str) -> Move:
    start_str, end_str = move.split("->")
    start = (8 - int(start_str[1:]), ord(start_str[0]) - 65)
    end = (8 - int(end_str[1:]), ord(end_str[0]) - 65)
    return start, end



def _simple_man_moves(board: Board, pos: Point, player: str) -> list[Point]:
    r, c = pos
    direction = -1 if player == "white" else 1
    moves: list[Point] = []
    for dc in (-1, 1):
        dest = (r + direction, c + dc)
        if within_bounds(dest) and is_empty(board, dest):
            moves.append(dest)
    return moves



def _simple_king_moves(board: Board, pos: Point, blocked_positions: Collection[Point] | None = None) -> list[Point]:
    blocked = normalize_blocked_positions(blocked_positions)
    r, c = pos
    moves: list[Point] = []
    for dr, dc in DIAGONALS:
        i, j = r + dr, c + dc
        while within_bounds((i, j)):
            if (i, j) in blocked or board[i][j] is not None:
                break
            moves.append((i, j))
            i += dr
            j += dc
    return moves


@log_time
def piece_capture_moves(
    board: Board,
    pos: Point,
    player: str,
    blocked_positions: Collection[Point] | None = None,
) -> list[Point]:
    piece = get_piece(board, pos)
    if not piece or owner(piece) != player:
        return []

    blocked = normalize_blocked_positions(blocked_positions)
    r, c = pos
    captures: list[Point] = []

    if piece.islower():
        for dr, dc in DIAGONALS:
            middle = (r + dr, c + dc)
            landing = (r + 2 * dr, c + 2 * dc)
            if not (within_bounds(middle) and within_bounds(landing)):
                continue
            if landing in blocked or not is_empty(board, landing):
                continue
            if is_opponent(get_piece(board, middle), player):
                captures.append(landing)
        return captures

    for dr, dc in DIAGONALS:
        i, j = r + dr, c + dc
        while within_bounds((i, j)):
            current = (i, j)
            if current in blocked:
                break
            piece_at = board[i][j]
            if piece_at is None:
                i += dr
                j += dc
                continue
            if owner(piece_at) == player:
                break
            i += dr
            j += dc
            while within_bounds((i, j)):
                landing = (i, j)
                if landing in blocked:
                    break
                if board[i][j] is not None:
                    break
                captures.append(landing)
                i += dr
                j += dc
            break

    return captures


@log_time
def man_moves(
    board: Board,
    pos: Point,
    player: str,
    blocked_positions: Collection[Point] | None = None,
) -> list[Point]:
    captures = piece_capture_moves(board, pos, player, blocked_positions=blocked_positions)
    if captures:
        return captures
    return _simple_man_moves(board, pos, player)


@log_time
def king_moves(
    board: Board,
    pos: Point,
    player: str,
    blocked_positions: Collection[Point] | None = None,
) -> list[Point]:
    captures = piece_capture_moves(board, pos, player, blocked_positions=blocked_positions)
    if captures:
        return captures
    return _simple_king_moves(board, pos, blocked_positions=blocked_positions)


@log_time
def any_capture(
    board: Board,
    player: str,
    blocked_positions: Collection[Point] | None = None,
    forced_start: Point | None = None,
) -> bool:
    if forced_start is not None:
        return bool(piece_capture_moves(board, forced_start, player, blocked_positions=blocked_positions))

    for row in range(8):
        for col in range(8):
            if piece_capture_moves(board, (row, col), player, blocked_positions=blocked_positions):
                return True
    return False



def legal_piece_moves(
    board: Board,
    pos: Point,
    player: str,
    blocked_positions: Collection[Point] | None = None,
    forced_start: Point | None = None,
) -> list[Point]:
    piece = get_piece(board, pos)
    if not piece or owner(piece) != player:
        return []
    if forced_start is not None and pos != forced_start:
        return []

    captures = piece_capture_moves(board, pos, player, blocked_positions=blocked_positions)
    if forced_start is not None:
        return captures
    if any_capture(board, player, blocked_positions=blocked_positions):
        return captures
    return _simple_man_moves(board, pos, player) if piece.islower() else _simple_king_moves(board, pos)



def captured_piece_for_move(
    board: Board,
    start: Point,
    end: Point,
    player: str,
    blocked_positions: Collection[Point] | None = None,
) -> Point | None:
    blocked = normalize_blocked_positions(blocked_positions)
    sr, sc = start
    er, ec = end
    dr = er - sr
    dc = ec - sc
    if abs(dr) != abs(dc) or dr == 0:
        return None

    step_r = sign(dr)
    step_c = sign(dc)
    r, c = sr + step_r, sc + step_c
    captured: Point | None = None

    while (r, c) != (er, ec):
        current = (r, c)
        if current in blocked:
            return None
        piece = board[r][c]
        if piece is not None:
            if owner(piece) == player or captured is not None:
                return None
            captured = current
        r += step_r
        c += step_c

    return captured



def _promote_piece(piece: str, end: Point) -> str:
    row, _ = end
    if piece == "w" and row == 0:
        return "W"
    if piece == "b" and row == 7:
        return "B"
    return piece



def apply_move(
    board: Board,
    start: Point,
    end: Point,
    player: str,
    blocked_positions: Collection[Point] | None = None,
    forced_start: Point | None = None,
) -> tuple[Board, Point | None]:
    sr, sc = start
    er, ec = end
    if not (within_bounds(start) and within_bounds(end)):
        raise ValueError("Позиция вне доски")

    piece = board[sr][sc]
    if not piece or owner(piece) != player:
        raise ValueError("Неверный ход")
    if board[er][ec] is not None:
        raise ValueError("Неверный ход")
    if forced_start is not None and start != forced_start:
        raise ValueError("Нужно продолжить взятие той же шашкой")

    possible_moves = legal_piece_moves(
        board,
        start,
        player,
        blocked_positions=blocked_positions,
        forced_start=forced_start,
    )
    if not possible_moves:
        if forced_start is not None:
            raise ValueError("Нужно продолжить взятие")
        if any_capture(board, player, blocked_positions=blocked_positions):
            raise ValueError("Обязательное взятие")
        raise ValueError("Неверный ход")
    if end not in possible_moves:
        raise ValueError("Неверный ход")

    captured = captured_piece_for_move(board, start, end, player, blocked_positions=blocked_positions)

    new_board = [row[:] for row in board]
    new_board[sr][sc] = None
    if captured is not None:
        new_board[captured[0]][captured[1]] = None
    new_board[er][ec] = _promote_piece(piece, end)
    return new_board, captured


@log_time
def validate_move(
    board: Board,
    start: Point,
    end: Point,
    player: str,
    blocked_positions: Collection[Point] | None = None,
    forced_start: Point | None = None,
) -> Board:
    new_board, _ = apply_move(
        board,
        start,
        end,
        player,
        blocked_positions=blocked_positions,
        forced_start=forced_start,
    )
    return new_board



def _generate_capture_sequences(
    board: Board,
    pos: Point,
    player: str,
    blocked_positions: tuple[Point, ...] = (),
) -> list[TurnSequence]:
    capture_moves = piece_capture_moves(board, pos, player, blocked_positions=blocked_positions)
    if not capture_moves:
        return []

    results: list[TurnSequence] = []
    for dest in capture_moves:
        new_board, captured = apply_move(
            board,
            pos,
            dest,
            player,
            blocked_positions=blocked_positions,
            forced_start=pos,
        )
        if captured is None:
            continue
        next_blocked = blocked_positions + (captured,)
        next_sequences = _generate_capture_sequences(new_board, dest, player, blocked_positions=next_blocked)
        if next_sequences:
            for seq in next_sequences:
                results.append(
                    TurnSequence(
                        steps=((pos, dest),) + seq.steps,
                        board=seq.board,
                        captured_positions=(captured,) + seq.captured_positions,
                    )
                )
        else:
            results.append(
                TurnSequence(
                    steps=((pos, dest),),
                    board=new_board,
                    captured_positions=(captured,),
                )
            )
    return results



def generate_turn_sequences(board: Board, player: str) -> list[TurnSequence]:
    capture_sequences: list[TurnSequence] = []

    for row in range(8):
        for col in range(8):
            piece = board[row][col]
            if not piece or owner(piece) != player:
                continue
            capture_sequences.extend(_generate_capture_sequences(board, (row, col), player))

    if capture_sequences:
        return capture_sequences

    quiet_sequences: list[TurnSequence] = []
    for row in range(8):
        for col in range(8):
            piece = board[row][col]
            if not piece or owner(piece) != player:
                continue
            simple_moves = _simple_man_moves(board, (row, col), player) if piece.islower() else _simple_king_moves(board, (row, col))
            for dest in simple_moves:
                new_board, _ = apply_move(board, (row, col), dest, player)
                quiet_sequences.append(TurnSequence(steps=(((row, col), dest),), board=new_board))

    return quiet_sequences


@log_time
def game_status(board: Board) -> Optional[str]:
    white_has_piece = False
    black_has_piece = False
    white_can_move = False
    black_can_move = False

    for row in range(8):
        for col in range(8):
            piece = board[row][col]
            if not piece:
                continue
            piece_owner = owner(piece)
            if piece_owner == "white":
                white_has_piece = True
                if not white_can_move and legal_piece_moves(board, (row, col), "white"):
                    white_can_move = True
            else:
                black_has_piece = True
                if not black_can_move and legal_piece_moves(board, (row, col), "black"):
                    black_can_move = True

    if not black_has_piece or not black_can_move:
        return "white_win"
    if not white_has_piece or not white_can_move:
        return "black_win"
    return None



def rebuild_board_from_moves(moves: Sequence[Move]) -> Board:
    board = create_initial_board()
    player = "white"
    forced_start: Point | None = None
    blocked_positions: tuple[Point, ...] = ()

    for start, end in moves:
        board, captured = apply_move(
            board,
            start,
            end,
            player,
            blocked_positions=blocked_positions,
            forced_start=forced_start,
        )
        if captured is not None:
            blocked_positions = blocked_positions + (captured,)
            if piece_capture_moves(board, end, player, blocked_positions=blocked_positions):
                forced_start = end
                continue
        forced_start = None
        blocked_positions = ()
        player = opponent(player)

    return board



def rebuild_board_from_history(history: Iterable[str], index: int | None = None) -> Board:
    moves = [parse_move(move) for move in history]
    if index is not None:
        moves = moves[:index]
    return rebuild_board_from_moves(moves)

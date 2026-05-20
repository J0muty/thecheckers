from __future__ import annotations

import uuid
import logging
from fastapi import Request, APIRouter, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Tuple

from src.settings.settings import templates
from src.app.game.draw_logic import (
    rebuild_draw_state_from_history,
    update_draw_state,
)
from src.app.game.game_logic import (
    apply_move,
    format_move,
    game_status,
    opponent,
    piece_capture_moves,
)
from src.app.routers.ws_router import single_board_manager
from src.app.game.single_logic import bot_turn, legal_moves
from src.base.single_redis import (
    clear_chain_state,
    game_exists,
    get_board_state,
    save_board_state,
    get_history,
    append_history,
    get_current_timers,
    apply_move_timer,
    apply_same_turn_timer,
    freeze_timers,
    get_board_state_at,
    expire_board,
    assign_user_game,
    get_user_game,
    get_game_user,
    get_chain_state,
    save_chain_state,
    get_draw_state,
    save_draw_state,
    clear_draw_state,
)
from src.base.postgres import record_game, save_recorded_game
from src.app.achievements.bots import check_bot_achievements
from src.app.utils.guest import is_guest

logger = logging.getLogger(__name__)

Board = List[List[Optional[str]]]
Point = Tuple[int, int]

single_router = APIRouter()
game_difficulties: dict[str, str] = {}
game_colors: dict[str, str] = {}


def _blocked_positions(chain_state: dict | None) -> list[Point]:
    if not chain_state:
        return []
    return [tuple(pos) for pos in chain_state.get("captured_positions", [])]


def _forced_piece(chain_state: dict | None) -> Point | None:
    if not chain_state or "piece" not in chain_state:
        return None
    piece = chain_state.get("piece")
    return tuple(piece) if piece else None


def _forced_payload(board: Board, chain_state: dict | None) -> tuple[Point | None, list[Point]]:
    forced_piece = _forced_piece(chain_state)
    if forced_piece is None or not chain_state:
        return None, []
    moves = piece_capture_moves(
        board,
        forced_piece,
        chain_state["player"],
        blocked_positions=_blocked_positions(chain_state),
    )
    return forced_piece, moves


def _turn_start_board(board: Board, chain_state: dict | None) -> Board:
    if chain_state and isinstance(chain_state.get("turn_start_board"), list):
        return chain_state["turn_start_board"]
    return board


def _turn_piece_was_king(board: Board, start: Point, chain_state: dict | None) -> bool:
    if chain_state and "start_piece_is_king" in chain_state:
        return bool(chain_state["start_piece_is_king"])
    piece = board[start[0]][start[1]]
    return bool(piece and piece.isupper())


def _piece_count(board: Board) -> int:
    return sum(1 for row in board for piece in row if piece)


async def _load_draw_state(game_id: str, history: list[str]) -> dict:
    state = await get_draw_state(game_id)
    if state is not None:
        return state
    rebuilt = rebuild_draw_state_from_history(history)
    await save_draw_state(game_id, rebuilt)
    return rebuilt


async def _run_bot_turn(
    game_id: str,
    board: Board,
    history: list[str],
    draw_state: dict,
    bot_color: str,
    human_color: str,
) -> MoveResult:
    difficulty = game_difficulties.get(game_id, "easy")
    bot_start_board = board
    bot_board, starts, ends = await bot_turn(board, bot_color, difficulty)
    timers = await get_current_timers(game_id, create=False) or await get_current_timers(game_id)

    for index, (start, end) in enumerate(zip(starts, ends)):
        notation = format_move(start, end)
        history.append(notation)
        await append_history(game_id, notation)
        if index + 1 < len(starts):
            await apply_same_turn_timer(game_id, bot_color)
        else:
            timers = await apply_move_timer(game_id, bot_color)

    await save_board_state(game_id, bot_board)

    status = game_status(bot_board)
    if timers[bot_color] <= 0:
        status = human_color + "_win"
    if status is None and starts and ends:
        moved_piece = bot_start_board[starts[0][0]][starts[0][1]]
        draw_state, draw_status = update_draw_state(
            draw_state,
            bot_start_board,
            bot_board,
            bot_color,
            human_color,
            moved_piece_was_king=bool(moved_piece and moved_piece.isupper()),
            was_capture=_piece_count(bot_start_board) != _piece_count(bot_board),
            was_promotion=bool(
                moved_piece
                and moved_piece.islower()
                and bot_board[ends[-1][0]][ends[-1][1]]
                and bot_board[ends[-1][0]][ends[-1][1]].isupper()
            ),
        )
        await save_draw_state(game_id, draw_state)
        if draw_status:
            status = draw_status

    if status:
        await _log_game_result(game_id, status)
        await freeze_timers(game_id)
        timers = await get_current_timers(game_id, create=False)
        await clear_draw_state(game_id)
        await expire_board(game_id, delay=600)
    else:
        timers = await get_current_timers(game_id)

    result = MoveResult(board=bot_board, status=status, history=history, timers=timers)
    await single_board_manager.broadcast(game_id, result.json())
    return result


async def _log_game_result(game_id: str, status: str):
    user = await get_game_user(game_id)
    if not user:
        return
    color = game_colors.get(game_id, "white")
    if status == "draw":
        res = "draw"
    elif status == "white_win":
        res = "win" if color == "white" else "loss"
    elif status == "black_win":
        res = "win" if color == "black" else "loss"
    else:
        return
    history = await get_history(game_id)
    difficulty = game_difficulties.get(game_id, "easy")
    white_id = int(user) if (color == "white" and str(user).isdigit()) else None
    black_id = int(user) if (color == "black" and str(user).isdigit()) else None
    saved = await save_recorded_game(
        game_id,
        white_id,
        black_id,
        history,
        status,
        mode="single",
        ranked=False,
    )
    if not saved:
        game_difficulties.pop(game_id, None)
        game_colors.pop(game_id, None)
        return
    if str(user).isdigit():
        await record_game(int(user), f"single_{difficulty}", res, None, game_id=game_id)
        await check_bot_achievements(int(user), difficulty, res)
    game_difficulties.pop(game_id, None)
    game_colors.pop(game_id, None)


class MoveRequest(BaseModel):
    start: Point
    end: Point
    player: str
    history_len: int


class Timers(BaseModel):
    white: float
    black: float
    turn: str


class BoardState(BaseModel):
    board: Board
    history: List[str]
    timers: Timers
    players: Optional[dict[str, str]] = None
    forced_piece: Optional[Point] = None
    forced_moves: List[Point] = Field(default_factory=list)


class MoveResult(BaseModel):
    board: Board
    status: Optional[str]
    history: List[str]
    timers: Timers
    forced_piece: Optional[Point] = None
    forced_moves: List[Point] = Field(default_factory=list)


class PlayerAction(BaseModel):
    player: str


class StartGame(BaseModel):
    difficulty: str
    color: str


@single_router.post("/api/single/start")
async def api_single_start(request: Request, req: StartGame):
    user_id = request.session.get("user_id")
    if user_id:
        existing = await get_user_game(str(user_id))
        if existing and await game_exists(existing):
            return JSONResponse({"game_id": existing})
    game_id = str(uuid.uuid4())
    game_difficulties[game_id] = req.difficulty
    game_colors[game_id] = req.color
    await get_board_state(game_id)
    if user_id:
        await assign_user_game(str(user_id), game_id)
    return JSONResponse({"game_id": game_id})


@single_router.get("/singleplayer", name="singleplayer")
async def single_redirect(
    request: Request, difficulty: str = "easy", color: str = "white"
):
    user_id = request.session.get("user_id")
    if user_id:
        existing = await get_user_game(str(user_id))
        if existing and await game_exists(existing):
            url = request.url_for("single_page", game_id=existing)
            return RedirectResponse(url)
    game_id = str(uuid.uuid4())
    game_difficulties[game_id] = difficulty
    game_colors[game_id] = color
    await get_board_state(game_id)
    if user_id:
        await assign_user_game(str(user_id), game_id)
    url = request.url_for("single_page", game_id=game_id)
    return RedirectResponse(url)


@single_router.get(
    "/singleplayer/{game_id}", response_class=HTMLResponse, name="single_page"
)
async def single_page(request: Request, game_id: str):
    if game_id in {"undefined", "null", ""} or not await game_exists(game_id):
        url = request.url_for("singleplayer")
        return RedirectResponse(url)
    difficulty = game_difficulties.get(game_id, "easy")
    color = game_colors.get(game_id, "white")
    return templates.TemplateResponse(
        "singleplayer.html",
        {
            "request": request,
            "board_id": game_id,
            "player_color": color or "",
            "difficulty": difficulty,
        },
    )


@single_router.get("/api/single/board/{game_id}", response_model=BoardState)
async def api_get_board(game_id: str):
    if not await game_exists(game_id):
        raise HTTPException(status_code=404)
    board = await get_board_state(game_id)
    history = await get_history(game_id)
    color = game_colors.get(game_id, "white")
    if color == "black" and not history:
        difficulty = game_difficulties.get(game_id, "easy")
        start_board = board
        board, starts, ends = await bot_turn(board, "white", difficulty)
        for index, (start, end) in enumerate(zip(starts, ends)):
            await append_history(game_id, format_move(start, end))
            if index + 1 < len(starts):
                await apply_same_turn_timer(game_id, "white")
            else:
                await apply_move_timer(game_id, "white")
        await save_board_state(game_id, board)
        if starts and ends:
            draw_state = await _load_draw_state(game_id, [])
            moved_piece = start_board[starts[0][0]][starts[0][1]]
            draw_state, _ = update_draw_state(
                draw_state,
                start_board,
                board,
                "white",
                "black",
                moved_piece_was_king=bool(moved_piece and moved_piece.isupper()),
                was_capture=_piece_count(start_board) != _piece_count(board),
                was_promotion=bool(moved_piece and moved_piece.islower() and board[ends[-1][0]][ends[-1][1]] and board[ends[-1][0]][ends[-1][1]].isupper()),
            )
            await save_draw_state(game_id, draw_state)
        board = await get_board_state(game_id)
        history = await get_history(game_id)

    timers = await get_current_timers(game_id)
    players = {"white": "Вы", "black": "Бот"}
    if color == "black":
        players = {"white": "Бот", "black": "Вы"}
    chain_state = await get_chain_state(game_id)
    forced_piece, forced_moves = _forced_payload(board, chain_state)
    return BoardState(
        board=board,
        history=history,
        timers=timers,
        players=players,
        forced_piece=forced_piece,
        forced_moves=forced_moves,
    )


@single_router.get("/api/single/timers/{game_id}", response_model=Timers)
async def api_single_timers(game_id: str):
    if not await game_exists(game_id):
        raise HTTPException(status_code=404)
    timers = await get_current_timers(game_id)
    if timers is None:
        raise HTTPException(status_code=404)
    return timers


@single_router.get("/api/single/moves/{game_id}", response_model=List[Point])
async def api_get_moves(game_id: str, row: int, col: int, player: str):
    if player != game_colors.get(game_id, "white"):
        raise HTTPException(status_code=403, detail="Invalid player")

    if not await game_exists(game_id):
        raise HTTPException(status_code=404)
    board = await get_board_state(game_id, create=False)
    timers = await get_current_timers(game_id, create=False)
    if timers and timers.get("turn") != player:
        return []
    chain_state = await get_chain_state(game_id)
    return legal_moves(
        board,
        (row, col),
        player,
        blocked_positions=_blocked_positions(chain_state),
        forced_start=_forced_piece(chain_state),
    )


@single_router.get("/api/single/captures/{game_id}", response_model=List[Point])
async def api_get_captures(game_id: str, row: int, col: int, player: str):
    if player != game_colors.get(game_id, "white"):
        raise HTTPException(status_code=403, detail="Invalid player")
    if not await game_exists(game_id):
        raise HTTPException(status_code=404)
    board = await get_board_state(game_id, create=False)
    timers = await get_current_timers(game_id, create=False)
    if timers and timers.get("turn") != player:
        return []
    chain_state = await get_chain_state(game_id)
    forced_piece = _forced_piece(chain_state)
    if forced_piece is not None and forced_piece != (row, col):
        return []
    return piece_capture_moves(
        board,
        (row, col),
        player,
        blocked_positions=_blocked_positions(chain_state),
    )


@single_router.post("/api/single/move/{game_id}", response_model=MoveResult)
async def api_make_move(game_id: str, req: MoveRequest):
    if req.player != game_colors.get(game_id, "white"):
        raise HTTPException(status_code=403, detail="Invalid player")
    if not await game_exists(game_id):
        raise HTTPException(status_code=404)
    timers_check = await get_current_timers(game_id, create=False)
    if timers_check and timers_check.get("turn") != req.player:
        raise HTTPException(status_code=409, detail="Not your turn")
    board = await get_board_state(game_id, create=False)
    history_before = await get_history(game_id)
    if len(history_before) != req.history_len:
        raise HTTPException(status_code=409, detail="Out of sync")
    draw_state = await _load_draw_state(game_id, history_before)
    chain_state = await get_chain_state(game_id)
    forced_start = _forced_piece(chain_state)
    blocked_positions = _blocked_positions(chain_state)
    turn_start_board = _turn_start_board(board, chain_state)
    turn_piece_was_king = _turn_piece_was_king(board, req.start, chain_state)
    if chain_state and chain_state.get("player") != req.player:
        raise HTTPException(status_code=409, detail="Invalid forced move state")
    try:
        new_board, captured = apply_move(
            board,
            req.start,
            req.end,
            req.player,
            blocked_positions=blocked_positions,
            forced_start=forced_start,
        )
    except ValueError as e:
        logger.error(
            "Invalid move in game %s by %s: %s -> %s (%s). History: %s",
            game_id,
            req.player,
            req.start,
            req.end,
            e,
            history_before,
        )
        raise HTTPException(status_code=400, detail=str(e))
    move_notation = format_move(req.start, req.end)
    history = [*history_before, move_notation]
    await append_history(game_id, move_notation)

    forced_piece = None
    forced_moves: list[Point] = []
    if captured is not None:
        next_blocked = blocked_positions + [captured]
        forced_moves = piece_capture_moves(
            new_board,
            req.end,
            req.player,
            blocked_positions=next_blocked,
        )
        if forced_moves:
            forced_piece = req.end
            await save_board_state(game_id, new_board)
            await save_chain_state(
                game_id,
                {
                    "player": req.player,
                    "piece": list(req.end),
                    "captured_positions": [list(pos) for pos in next_blocked],
                    "turn_start_board": turn_start_board,
                    "start_piece_is_king": turn_piece_was_king,
                },
            )
            timers = await apply_same_turn_timer(game_id, req.player)
            if timers[req.player] <= 0:
                status = opponent(req.player) + "_win"
                await clear_chain_state(game_id)
                await _log_game_result(game_id, status)
                await freeze_timers(game_id)
                timers = await get_current_timers(game_id, create=False)
                await clear_draw_state(game_id)
                await expire_board(game_id, delay=600)
                result = MoveResult(
                    board=new_board,
                    status=status,
                    history=history,
                    timers=timers,
                )
                await single_board_manager.broadcast(game_id, result.json())
                return result
            result = MoveResult(
                board=new_board,
                status=None,
                history=history,
                timers=await get_current_timers(game_id),
                forced_piece=forced_piece,
                forced_moves=forced_moves,
            )
            await single_board_manager.broadcast(game_id, result.json())
            return result

    await clear_chain_state(game_id)
    await save_board_state(game_id, new_board)
    timers = await apply_move_timer(game_id, req.player)
    status = None
    if timers[req.player] <= 0:
        status = opponent(req.player) + "_win"
    if status is None:
        status = game_status(new_board)
    if status is None:
        draw_state, draw_status = update_draw_state(
            draw_state,
            turn_start_board,
            new_board,
            req.player,
            opponent(req.player),
            moved_piece_was_king=turn_piece_was_king,
            was_capture=captured is not None or bool(chain_state),
            was_promotion=bool((not turn_piece_was_king) and new_board[req.end[0]][req.end[1]] and new_board[req.end[0]][req.end[1]].isupper()),
        )
        await save_draw_state(game_id, draw_state)
        if draw_status:
            status = draw_status

    if status:
        await _log_game_result(game_id, status)
        await freeze_timers(game_id)
        timers = await get_current_timers(game_id, create=False)
        await clear_draw_state(game_id)
        await expire_board(game_id, delay=600)
        result = MoveResult(board=new_board, status=status, history=history, timers=timers)
        await single_board_manager.broadcast(game_id, result.json())
        return result

    result = MoveResult(board=new_board, status=None, history=history, timers=await get_current_timers(game_id))
    await single_board_manager.broadcast(game_id, result.json())
    return result


@single_router.post("/api/single/bot_move/{game_id}", response_model=MoveResult)
async def api_single_bot_move(game_id: str):
    if not await game_exists(game_id):
        raise HTTPException(status_code=404)
    human_color = game_colors.get(game_id, "white")
    bot_color = opponent(human_color)
    timers = await get_current_timers(game_id, create=False)
    if timers is None:
        raise HTTPException(status_code=404)
    board = await get_board_state(game_id, create=False)
    history = await get_history(game_id)
    if board is None:
        raise HTTPException(status_code=404)
    if timers.get("turn") != bot_color:
        return MoveResult(board=board, status=None, history=history, timers=timers)
    chain_state = await get_chain_state(game_id)
    if chain_state:
        return MoveResult(board=board, status=None, history=history, timers=timers)
    draw_state = await _load_draw_state(game_id, history)
    return await _run_bot_turn(game_id, board, history, draw_state, bot_color, human_color)


@single_router.get("/api/single/snapshot/{game_id}/{index}", response_model=Board)
async def api_board_snapshot(game_id: str, index: int):
    if not await game_exists(game_id):
        raise HTTPException(status_code=404)
    board = await get_board_state_at(game_id, index)
    return board


@single_router.post("/api/single/resign/{game_id}", response_model=MoveResult)
async def api_resign(game_id: str, req: PlayerAction):
    if req.player != game_colors.get(game_id, "white"):
        raise HTTPException(status_code=403, detail="Invalid player")
    if not await game_exists(game_id):
        raise HTTPException(status_code=404)
    board = await get_board_state(game_id, create=False)
    status = "black_win" if req.player == "white" else "white_win"
    await _log_game_result(game_id, status)
    history = await get_history(game_id)
    timers = await get_current_timers(game_id, create=False)
    await freeze_timers(game_id)
    await clear_draw_state(game_id)
    await expire_board(game_id, delay=600)
    result = MoveResult(board=board, status=status, history=history, timers=timers)
    await single_board_manager.broadcast(game_id, result.json())
    return result


@single_router.post("/api/single/check_timeout/{game_id}", response_model=MoveResult)
async def api_single_check_timeout(game_id: str):
    if not await game_exists(game_id):
        raise HTTPException(status_code=404)
    board = await get_board_state(game_id, create=False)
    timers = await get_current_timers(game_id, create=False)
    if board is None or timers is None:
        raise HTTPException(status_code=404)
    history = await get_history(game_id)
    active = timers.get("turn")
    if active not in ("white", "black"):
        return MoveResult(board=board, status=None, history=history, timers=timers)
    status = None
    if timers[active] <= 0:
        status = "black_win" if active == "white" else "white_win"
    if not status:
        return MoveResult(board=board, status=None, history=history, timers=timers)
    await _log_game_result(game_id, status)
    await freeze_timers(game_id)
    await clear_draw_state(game_id)
    await expire_board(game_id, delay=600)
    result = MoveResult(board=board, status=status, history=history, timers=timers)
    await single_board_manager.broadcast(game_id, result.json())
    return result

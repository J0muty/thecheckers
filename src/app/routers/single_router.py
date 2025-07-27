import uuid
import asyncio
import logging
from fastapi import Request, APIRouter, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from pydantic import BaseModel
from typing import List, Optional, Tuple

from src.settings.settings import templates
from src.app.game.game_logic import validate_move, piece_capture_moves, game_status
from src.app.routers.ws_router import single_board_manager
from src.app.game.single_logic import bot_turn, legal_moves
from src.base.single_redis import (
    game_exists,
    get_board_state,
    save_board_state,
    get_history,
    append_history,
    get_current_timers,
    apply_move_timer,
    apply_same_turn_timer,
    get_board_state_at,
    cleanup_board,
    assign_user_game,
    get_user_game,
    get_game_user,
)
from src.base.postgres import record_game, save_recorded_game

logger = logging.getLogger(__name__)

Board = List[List[Optional[str]]]
Point = Tuple[int, int]

single_router = APIRouter()
game_difficulties: dict[str, str] = {}
game_colors: dict[str, str] = {}


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
    white_id = int(user) if color == "white" else None
    black_id = int(user) if color == "black" else None
    await save_recorded_game(
        game_id,
        white_id,
        black_id,
        history,
        status,
        mode="single",
        ranked=False,
    )
    await record_game(int(user), "single", res, None, game_id=game_id)


class MoveRequest(BaseModel):
    start: Point
    end: Point
    player: str


class Timers(BaseModel):
    white: float
    black: float
    turn: str


class BoardState(BaseModel):
    board: Board
    history: List[str]
    timers: Timers
    players: Optional[dict[str, str]] = None


class MoveResult(BaseModel):
    board: Board
    status: Optional[str]
    history: List[str]
    timers: Timers


class PlayerAction(BaseModel):
    player: str


class StartGame(BaseModel):
    difficulty: str
    color: str


@single_router.post("/api/single/start")
async def api_single_start(request: Request, req: StartGame):
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401)
    existing = await get_user_game(str(user_id))
    if existing:
        return JSONResponse({"game_id": existing})
    game_id = str(uuid.uuid4())
    game_difficulties[game_id] = req.difficulty
    game_colors[game_id] = req.color
    await get_board_state(game_id)
    await assign_user_game(str(user_id), game_id)
    return JSONResponse({"game_id": game_id})


@single_router.get("/singleplayer", name="singleplayer")
async def single_redirect(
    request: Request, difficulty: str = "easy", color: str = "white"
):
    user_id = request.session.get("user_id")
    if user_id:
        existing = await get_user_game(str(user_id))
        if existing:
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
        board, starts, ends, boards = await bot_turn(board, "white", difficulty)
        moves = list(zip(starts, ends, boards))
        last_index = len(moves) - 1
        for i, (s, e, b) in enumerate(moves):
            await save_board_state(game_id, b)
            notation = f"{chr(s[1] + 65)}{8 - s[0]}->{chr(e[1] + 65)}{8 - e[0]}"
            await append_history(game_id, notation)
            if i < last_index:
                await apply_same_turn_timer(game_id, "white")
            else:
                await apply_move_timer(game_id, "white")
        board = await get_board_state(game_id)
        history = await get_history(game_id)

    timers = await get_current_timers(game_id)
    players = {"white": "Вы", "black": "Бот"}
    if color == "black":
        players = {"white": "Бот", "black": "Вы"}
    return BoardState(board=board, history=history, timers=timers, players=players)


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
    return legal_moves(board, (row, col), player)


@single_router.get("/api/single/captures/{game_id}", response_model=List[Point])
async def api_get_captures(game_id: str, row: int, col: int, player: str):
    if player != game_colors.get(game_id, "white"):
        raise HTTPException(status_code=403, detail="Invalid player")
    if not await game_exists(game_id):
        raise HTTPException(status_code=404)
    board = await get_board_state(game_id, create=False)
    return piece_capture_moves(board, (row, col), player)


@single_router.post("/api/single/move/{game_id}", response_model=MoveResult)
async def api_make_move(game_id: str, req: MoveRequest):
    if req.player != game_colors.get(game_id, "white"):
        raise HTTPException(status_code=403, detail="Invalid player")
    if not await game_exists(game_id):
        raise HTTPException(status_code=404)
    board = await get_board_state(game_id, create=False)
    history_before = await get_history(game_id)
    try:
        new_board = await validate_move(board, req.start, req.end, req.player)
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
    await save_board_state(game_id, new_board)
    move_notation = f"{chr(req.start[1] + 65)}{8 - req.start[0]}->{chr(req.end[1] + 65)}{8 - req.end[0]}"
    await append_history(game_id, move_notation)
    dr = abs(req.end[0] - req.start[0])
    dc = abs(req.end[1] - req.start[1])
    is_capture = dr > 1 or dc > 1
    if is_capture:
        more_captures = bool(piece_capture_moves(new_board, req.end, req.player))
        if more_captures:
            timers = await apply_same_turn_timer(game_id, req.player)
            if timers[req.player] <= 0:
                status = "black_win" if req.player == "white" else "white_win"
                await _log_game_result(game_id, status)
                history = await get_history(game_id)
                timers_view = await get_current_timers(game_id, create=False)
                await cleanup_board(game_id)
                result = MoveResult(
                    board=new_board,
                    status=status,
                    history=history,
                    timers=timers_view,
                )
                await single_board_manager.broadcast(game_id, result.json())
                return result
            history = await get_history(game_id)
            timers_view = await get_current_timers(game_id)
            result = MoveResult(
                board=new_board, status=None, history=history, timers=timers_view
            )
            await single_board_manager.broadcast(game_id, result.json())
            return result
        else:
            timers = await apply_move_timer(game_id, req.player)
    else:
        timers = await apply_move_timer(game_id, req.player)
    if timers[req.player] <= 0:
        status = "black_win" if req.player == "white" else "white_win"
        await _log_game_result(game_id, status)
        history = await get_history(game_id)
        timers_view = await get_current_timers(game_id, create=False)
        await cleanup_board(game_id)
        result = MoveResult(
            board=new_board,
            status=status,
            history=history,
            timers=timers_view,
        )
        await single_board_manager.broadcast(game_id, result.json())
        return result
    status = game_status(new_board)
    if status:
        await _log_game_result(game_id, status)
        history = await get_history(game_id)
        timers_view = await get_current_timers(game_id, create=False)
        await cleanup_board(game_id)
        result = MoveResult(
            board=new_board,
            status=status,
            history=history,
            timers=timers_view,
        )
        await single_board_manager.broadcast(game_id, result.json())
        return result
    else:
        bot_color = "black" if req.player == "white" else "white"
        difficulty = game_difficulties.get(game_id, "easy")
        new_board, starts, ends, boards = await bot_turn(
            new_board, bot_color, difficulty
        )
        moves = list(zip(starts, ends, boards))
        last_index = len(moves) - 1
        status = None
        for i, (s, e, b) in enumerate(moves):
            await save_board_state(game_id, b)
            notation = f"{chr(s[1] + 65)}{8 - s[0]}->{chr(e[1] + 65)}{8 - e[0]}"
            await append_history(game_id, notation)
            if i < last_index:
                await apply_same_turn_timer(game_id, bot_color)

            else:
                timers = await apply_move_timer(game_id, bot_color)
                if timers[bot_color] <= 0:
                    status = "white_win" if bot_color == "black" else "black_win"
            history = await get_history(game_id)
            timers_view = await get_current_timers(game_id)
            step_status = status if i == last_index else None
            result = MoveResult(
                board=b, status=step_status, history=history, timers=timers_view
            )
            await single_board_manager.broadcast(game_id, result.json())
            if i < last_index:
                await asyncio.sleep(0.5)

    if status is None:
        status = game_status(new_board)
    if status:
        await _log_game_result(game_id, status)
        history = await get_history(game_id)
        timers = await get_current_timers(game_id, create=False)
        await cleanup_board(game_id)
    else:
        history = await get_history(game_id)
        timers = await get_current_timers(game_id)
    result = MoveResult(board=new_board, status=status, history=history, timers=timers)
    await single_board_manager.broadcast(game_id, result.json())
    return result


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
    await cleanup_board(game_id)
    result = MoveResult(board=board, status=status, history=history, timers=timers)
    await single_board_manager.broadcast(game_id, result.json())
    return result


@single_router.post("/api/single/check_timeout/{game_id}", response_model=MoveResult)
async def api_single_check_timeout(game_id: str):
    if not await game_exists(game_id):
        raise HTTPException(status_code=404)
    board = await get_board_state(game_id, create=False)
    timers = await get_current_timers(game_id, create=False)
    history = await get_history(game_id)
    active = timers["turn"]
    status = None
    if timers[active] <= 0:
        status = "black_win" if active == "white" else "white_win"
    if not status:
        return MoveResult(board=board, status=None, history=history, timers=timers)
    await _log_game_result(game_id, status)
    await cleanup_board(game_id)
    result = MoveResult(board=board, status=status, history=history, timers=timers)
    await single_board_manager.broadcast(game_id, result.json())
    return result

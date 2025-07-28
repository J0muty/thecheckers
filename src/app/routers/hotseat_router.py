import uuid
import logging
from typing import List, Optional, Tuple

from fastapi import Request, APIRouter, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel

from src.settings.settings import templates
from src.app.game.game_logic import validate_move, piece_capture_moves, game_status
from src.base.redis import (
    assign_user_hotseat,
    get_user_board,
    get_user_hotseat,
    clear_user_hotseat,
    cancel_waiting,
)
from src.base.hotseat_redis import (
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
    get_game_user,
    cleanup_board,
)
from src.app.routers.ws_router import board_manager
from src.base.postgres import record_game, save_recorded_game

logger = logging.getLogger(__name__)

Board = List[List[Optional[str]]]
Point = Tuple[int, int]

hotseat_router = APIRouter()


async def _log_game_result(board_id: str, status: str):
    user = await get_game_user(board_id)
    if not user:
        return
    history = await get_history(board_id)
    await save_recorded_game(
        board_id,
        None,
        None,
        history,
        status,
        mode="hotseat",
        ranked=False,
    )
    await record_game(int(user), "hotseat", status, None, game_id=board_id)


async def is_finished(board_id: str) -> bool:
    timers = await get_current_timers(board_id, create=False)
    return timers is not None and timers.get("turn") == "stopped"


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


class MoveResult(BaseModel):
    board: Board
    status: Optional[str]
    history: List[str]
    timers: Timers


@hotseat_router.get("/hotseat", name="hotseat")
async def hotseat_redirect(request: Request):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse("/login")
    existing_hotseat = await get_user_hotseat(str(user_id))
    if existing_hotseat:
        await cleanup_board(existing_hotseat)
        await clear_user_hotseat(str(user_id))
    existing_board = await get_user_board(str(user_id))
    if existing_board:
        await cleanup_board(existing_board)
    await cancel_waiting(str(user_id))
    board_id = str(uuid.uuid4())
    await get_board_state(board_id)
    await assign_user_hotseat(str(user_id), board_id)
    url = request.url_for("hotseat_page", board_id=board_id)
    return RedirectResponse(url)


@hotseat_router.get("/hotseat/{board_id}", response_class=HTMLResponse, name="hotseat_page")
async def hotseat_page(request: Request, board_id: str):
    if not await game_exists(board_id):
        raise HTTPException(status_code=404)
    session_user = request.session.get("user_id")
    finished = await is_finished(board_id)
    if finished and session_user:
        await clear_user_hotseat(str(session_user))
    if session_user and not finished:
        await assign_user_hotseat(str(session_user), board_id)
    return templates.TemplateResponse(
        "hotseat.html",
        {"request": request, "board_id": board_id, "player_color": ""},
    )


@hotseat_router.get("/api/hotseat/board/{board_id}", response_model=BoardState)
async def api_hotseat_board(board_id: str):
    if not await game_exists(board_id):
        raise HTTPException(status_code=404)
    board = await get_board_state(board_id)
    history = await get_history(board_id)
    timers = await get_current_timers(board_id, create=False) or await get_current_timers(board_id)
    return BoardState(board=board, history=history, timers=timers)


@hotseat_router.get("/api/hotseat/timers/{board_id}", response_model=Timers)
async def api_hotseat_timers(board_id: str):
    if not await game_exists(board_id):
        raise HTTPException(status_code=404)
    timers = await get_current_timers(board_id)
    if timers is None:
        raise HTTPException(status_code=404)
    return timers


@hotseat_router.get("/api/hotseat/moves/{board_id}", response_model=List[Point])
async def api_hotseat_moves(board_id: str, row: int, col: int, player: str):
    if not await game_exists(board_id):
        raise HTTPException(status_code=404)
    board = await get_board_state(board_id, create=False)
    moves: List[Point] = []
    for r in range(8):
        for c in range(8):
            try:
                await validate_move(board, (row, col), (r, c), player)
                moves.append((r, c))
            except ValueError:
                pass
    return moves


@hotseat_router.get("/api/hotseat/captures/{board_id}", response_model=List[Point])
async def api_hotseat_captures(board_id: str, row: int, col: int, player: str):
    if not await game_exists(board_id):
        raise HTTPException(status_code=404)
    board = await get_board_state(board_id, create=False)
    return piece_capture_moves(board, (row, col), player)


@hotseat_router.post("/api/hotseat/move/{board_id}", response_model=MoveResult)
async def api_hotseat_move(board_id: str, req: MoveRequest):
    if not await game_exists(board_id):
        raise HTTPException(status_code=404)
    timers_check = await get_current_timers(board_id, create=False)
    if timers_check and timers_check.get("turn") not in ("white", "black"):
        raise HTTPException(status_code=400, detail="Game finished")
    board = await get_board_state(board_id, create=False)
    try:
        new_board = await validate_move(board, req.start, req.end, req.player)
    except ValueError as e:
        raise ValueError(str(e))
    await save_board_state(board_id, new_board)
    move_notation = f"{chr(req.start[1] + 65)}{8 - req.start[0]}->{chr(req.end[1] + 65)}{8 - req.end[0]}"
    await append_history(board_id, move_notation)
    dr = abs(req.end[0] - req.start[0])
    dc = abs(req.end[1] - req.start[1])
    is_capture = dr > 1 or dc > 1
    if is_capture:
        more_captures = bool(piece_capture_moves(new_board, req.end, req.player))
        if more_captures:
            timers = await apply_same_turn_timer(board_id, req.player)
        else:
            timers = await apply_move_timer(board_id, req.player)
    else:
        timers = await apply_move_timer(board_id, req.player)
    status = None
    if timers[req.player] <= 0:
        status = "black_win" if req.player == "white" else "white_win"
    else:
        status = game_status(new_board)
    history = await get_history(board_id)
    if status:
        await _log_game_result(board_id, status)
        await freeze_timers(board_id)
        timers_view = await get_current_timers(board_id, create=False)
        await expire_board(board_id, delay=600)
    else:
        timers_view = await get_current_timers(board_id)
    result = MoveResult(
        board=new_board, status=status, history=history, timers=timers_view
    )
    await board_manager.broadcast(board_id, result.json())
    return result


@hotseat_router.get("/api/hotseat/snapshot/{board_id}/{index}", response_model=Board)
async def api_hotseat_snapshot(board_id: str, index: int):
    if not await game_exists(board_id):
        raise HTTPException(status_code=404)
    board = await get_board_state_at(board_id, index)
    return board


@hotseat_router.post("/api/hotseat/check_timeout/{board_id}", response_model=MoveResult)
async def api_hotseat_check_timeout(board_id: str):
    if not await game_exists(board_id):
        raise HTTPException(status_code=404)
    board = await get_board_state(board_id, create=False)
    timers = await get_current_timers(board_id, create=False)
    history = await get_history(board_id)
    active = timers["turn"]
    status = None
    if timers[active] <= 0:
        status = "black_win" if active == "white" else "white_win"
    if status:
        await _log_game_result(board_id, status)
        await freeze_timers(board_id)
        timers = await get_current_timers(board_id, create=False)
        await expire_board(board_id, delay=600)
    result = MoveResult(board=board, status=status, history=history, timers=timers)
    await board_manager.broadcast(board_id, result.json())
    return result


@hotseat_router.post("/api/hotseat/end/{board_id}", response_model=MoveResult)
async def api_hotseat_end(request: Request, board_id: str):
    if not await game_exists(board_id):
        raise HTTPException(status_code=404)
    board = await get_board_state(board_id, create=False)
    history = await get_history(board_id)
    await _log_game_result(board_id, "ended")
    await freeze_timers(board_id)
    timers = await get_current_timers(board_id, create=False)
    await expire_board(board_id, delay=600)
    user_id = request.session.get("user_id")
    if user_id:
        await clear_user_hotseat(str(user_id))
    result = MoveResult(board=board, status="ended", history=history, timers=timers)
    await board_manager.broadcast(board_id, result.json())
    return result

import uuid
import logging
from typing import List, Optional, Tuple

from fastapi import Request, APIRouter, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field

from src.settings.settings import templates
from src.app.game.draw_logic import (
    rebuild_draw_state_from_history,
    update_draw_state,
)
from src.app.game.game_logic import apply_move, format_move, game_status, legal_piece_moves, opponent, piece_capture_moves
from src.base.redis import (
    assign_user_hotseat,
    get_user_board,
    get_user_hotseat,
    clear_user_hotseat,
    cancel_waiting,
    get_user_move_input_mode,
)
from src.base.hotseat_redis import (
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
    get_game_user,
    cleanup_board,
    get_chain_state,
    save_chain_state,
    get_draw_state,
    save_draw_state,
    clear_draw_state,
)
from src.app.routers.ws_router import board_manager
from src.base.postgres import get_selected_checker_skins, record_game, save_recorded_game
from src.app.utils.guest import is_guest

logger = logging.getLogger(__name__)

Board = List[List[Optional[str]]]
Point = Tuple[int, int]

hotseat_router = APIRouter()


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


async def _load_draw_state(board_id: str, history: list[str]) -> dict:
    state = await get_draw_state(board_id)
    if state is not None:
        return state
    rebuilt = rebuild_draw_state_from_history(history)
    await save_draw_state(board_id, rebuilt)
    return rebuilt


async def _log_game_result(board_id: str, status: str):
    user = await get_game_user(board_id)
    if not user or is_guest(str(user)):
        return
    history = await get_history(board_id)
    saved = await save_recorded_game(
        board_id,
        None,
        None,
        history,
        status,
        mode="hotseat",
        ranked=False,
    )
    if not saved:
        return
    if str(user).isdigit():
        await record_game(int(user), "hotseat", status, None, game_id=board_id)


async def is_finished(board_id: str) -> bool:
    timers = await get_current_timers(board_id, create=False)
    return timers is not None and timers.get("turn") == "stopped"


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
    skins: dict[str, str] = Field(default_factory=dict)
    forced_piece: Optional[Point] = None
    forced_moves: List[Point] = Field(default_factory=list)


class MoveResult(BaseModel):
    board: Board
    status: Optional[str]
    history: List[str]
    timers: Timers
    forced_piece: Optional[Point] = None
    forced_moves: List[Point] = Field(default_factory=list)


@hotseat_router.get("/hotseat", name="hotseat")
async def hotseat_redirect(request: Request):
    user_id = request.session.get("user_id")
    existing_hotseat = await get_user_hotseat(str(user_id))
    if existing_hotseat:
        await cleanup_board(existing_hotseat)
        await clear_user_hotseat(str(user_id))
    existing_board = await get_user_board(str(user_id))
    if existing_board:
        await cleanup_board(existing_board)
    await cancel_waiting(str(user_id))
    board_id = str(uuid.uuid4())
    await assign_user_hotseat(str(user_id), board_id)
    await get_board_state(board_id)
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
    move_input_mode = "click"
    if session_user and not is_guest(session_user):
        move_input_mode = await get_user_move_input_mode(session_user)
    return templates.TemplateResponse(
        "hotseat.html",
        {
            "request": request,
            "board_id": board_id,
            "player_color": "",
            "move_input_mode": move_input_mode,
        },
    )


@hotseat_router.get("/api/hotseat/board/{board_id}", response_model=BoardState)
async def api_hotseat_board(board_id: str):
    if not await game_exists(board_id):
        raise HTTPException(status_code=404)
    board = await get_board_state(board_id)
    history = await get_history(board_id)
    timers = await get_current_timers(board_id, create=False) or await get_current_timers(board_id)
    chain_state = await get_chain_state(board_id)
    forced_piece, forced_moves = _forced_payload(board, chain_state)
    user_id = await get_game_user(board_id)
    hotseat_user_id = int(user_id) if user_id and str(user_id).isdigit() else None
    skins = await get_selected_checker_skins({"white": hotseat_user_id, "black": hotseat_user_id})
    return BoardState(
        board=board,
        history=history,
        timers=timers,
        skins=skins,
        forced_piece=forced_piece,
        forced_moves=forced_moves,
    )


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
    timers = await get_current_timers(board_id, create=False)
    if timers and timers.get("turn") != player:
        return []
    chain_state = await get_chain_state(board_id)
    return legal_piece_moves(
        board,
        (row, col),
        player,
        blocked_positions=_blocked_positions(chain_state),
        forced_start=_forced_piece(chain_state),
    )


@hotseat_router.get("/api/hotseat/captures/{board_id}", response_model=List[Point])
async def api_hotseat_captures(board_id: str, row: int, col: int, player: str):
    if not await game_exists(board_id):
        raise HTTPException(status_code=404)
    board = await get_board_state(board_id, create=False)
    timers = await get_current_timers(board_id, create=False)
    if timers and timers.get("turn") != player:
        return []
    chain_state = await get_chain_state(board_id)
    forced_piece = _forced_piece(chain_state)
    if forced_piece is not None and forced_piece != (row, col):
        return []
    return piece_capture_moves(
        board,
        (row, col),
        player,
        blocked_positions=_blocked_positions(chain_state),
    )


@hotseat_router.post("/api/hotseat/move/{board_id}", response_model=MoveResult)
async def api_hotseat_move(board_id: str, req: MoveRequest):
    if not await game_exists(board_id):
        raise HTTPException(status_code=404)
    timers_check = await get_current_timers(board_id, create=False)
    if timers_check and timers_check.get("turn") not in ("white", "black"):
        raise HTTPException(status_code=400, detail="Game finished")
    if timers_check and timers_check.get("turn") != req.player:
        raise HTTPException(status_code=409, detail="Not your turn")
    board = await get_board_state(board_id, create=False)
    history = await get_history(board_id)
    if len(history) != req.history_len:
        raise HTTPException(status_code=409, detail="Out of sync")
    draw_state = await _load_draw_state(board_id, history)
    chain_state = await get_chain_state(board_id)
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
        raise HTTPException(status_code=400, detail=str(e))
    move_notation = format_move(req.start, req.end)
    history.append(move_notation)
    await append_history(board_id, move_notation)

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
            await save_board_state(board_id, new_board)
            await save_chain_state(
                board_id,
                {
                    "player": req.player,
                    "piece": list(req.end),
                    "captured_positions": [list(pos) for pos in next_blocked],
                    "turn_start_board": turn_start_board,
                    "start_piece_is_king": turn_piece_was_king,
                },
            )
            timers = await apply_same_turn_timer(board_id, req.player)
            status = None
            if timers[req.player] <= 0:
                status = opponent(req.player) + "_win"
                await clear_chain_state(board_id)
                await _log_game_result(board_id, status)
                await freeze_timers(board_id)
                timers = await get_current_timers(board_id, create=False)
                await clear_draw_state(board_id)
                await expire_board(board_id, delay=600)
                result = MoveResult(board=new_board, status=status, history=history, timers=timers)
                await board_manager.broadcast(board_id, result.json())
                return result
            result = MoveResult(
                board=new_board,
                status=None,
                history=history,
                timers=await get_current_timers(board_id),
                forced_piece=forced_piece,
                forced_moves=forced_moves,
            )
            await board_manager.broadcast(board_id, result.json())
            return result

    await clear_chain_state(board_id)
    await save_board_state(board_id, new_board)
    timers = await apply_move_timer(board_id, req.player)
    status = None
    if timers[req.player] <= 0:
        status = "black_win" if req.player == "white" else "white_win"
    else:
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
        await save_draw_state(board_id, draw_state)
        if draw_status:
            status = draw_status
    if status:
        await _log_game_result(board_id, status)
        await freeze_timers(board_id)
        timers_view = await get_current_timers(board_id, create=False)
        await clear_draw_state(board_id)
        await expire_board(board_id, delay=600)
    else:
        timers_view = await get_current_timers(board_id)
    result = MoveResult(
        board=new_board,
        status=status,
        history=history,
        timers=timers_view,
        forced_piece=forced_piece,
        forced_moves=forced_moves,
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
    active = timers.get("turn")
    if active not in ("white", "black"):
        return MoveResult(board=board, status=None, history=history, timers=timers)
    status = None
    if timers[active] <= 0:
        status = "black_win" if active == "white" else "white_win"
    if status:
        await _log_game_result(board_id, status)
        await freeze_timers(board_id)
        timers = await get_current_timers(board_id, create=False)
        await clear_draw_state(board_id)
        await expire_board(board_id, delay=600)
    result = MoveResult(board=board, status=status, history=history, timers=timers)
    await board_manager.broadcast(board_id, result.json())
    return result


@hotseat_router.post("/api/hotseat/end/{board_id}", response_model=MoveResult)
async def api_hotseat_end(request: Request, board_id: str):
    if not await game_exists(board_id):
        raise HTTPException(status_code=404)
    if await is_finished(board_id):
        raise HTTPException(status_code=400, detail="Game finished")
    board = await get_board_state(board_id, create=False)
    history = await get_history(board_id)
    await _log_game_result(board_id, "ended")
    await freeze_timers(board_id)
    timers = await get_current_timers(board_id, create=False)
    await clear_draw_state(board_id)
    await expire_board(board_id, delay=600)
    user_id = request.session.get("user_id")
    if user_id:
        await clear_user_hotseat(str(user_id))
    result = MoveResult(board=board, status="ended", history=history, timers=timers)
    await board_manager.broadcast(board_id, result.json())
    return result


@hotseat_router.post("/api/hotseat/draw/{board_id}", response_model=MoveResult)
async def api_hotseat_draw(request: Request, board_id: str):
    if not await game_exists(board_id):
        raise HTTPException(status_code=404)
    if await is_finished(board_id):
        raise HTTPException(status_code=400, detail="Game finished")
    board = await get_board_state(board_id, create=False)
    history = await get_history(board_id)
    await _log_game_result(board_id, "draw")
    await freeze_timers(board_id)
    timers = await get_current_timers(board_id, create=False)
    await clear_draw_state(board_id)
    await expire_board(board_id, delay=600)
    user_id = request.session.get("user_id")
    if user_id:
        await clear_user_hotseat(str(user_id))
    result = MoveResult(board=board, status="draw", history=history, timers=timers)
    await board_manager.broadcast(board_id, result.json())
    return result

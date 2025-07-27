import uuid
import json
import logging
from fastapi import Request, APIRouter, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
from typing import List, Optional, Tuple
from src.app.routers.ws_router import board_manager

from src.settings.settings import templates
from src.base.redis import (
    board_exists,
    get_board_state,
    save_board_state,
    assign_user_board,
    get_history,
    append_history,
    get_current_timers,
    apply_move_timer,
    apply_same_turn_timer,
    get_board_state_at,
    get_board_players,
    cleanup_board,
    set_draw_offer,
    get_draw_offer,
    clear_draw_offer,
)
from src.base.lobby_redis import clear_lobby_board
from src.app.game.game_logic import (
    validate_move,
    piece_capture_moves,
    game_status,
    man_moves,
    king_moves,
    owner,
)
from src.base.postgres import (
    record_game_result,
    get_user_stats,
    get_user_login,
    record_game,
    save_recorded_game,
)

logger = logging.getLogger(__name__)

Board = List[List[Optional[str]]]
Point = Tuple[int, int]

board_router = APIRouter()

def determine_win_reason(board: Board, winner: str) -> str:
    opponent = "black" if winner == "white" else "white"
    has_piece = False
    can_move = False
    for r in range(8):
        for c in range(8):
            p = board[r][c]
            if not p or owner(p) != opponent:
                continue
            has_piece = True
            moves = (
                man_moves(board, (r, c), opponent)
                if p.islower()
                else king_moves(board, (r, c), opponent)
            )
            caps = piece_capture_moves(board, (r, c), opponent)
            if moves or caps:
                can_move = True
    if not has_piece:
        return "no_pieces"
    if not can_move:
        return "no_moves"
    return "unknown"


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
    rating_change: Optional[dict[str, int]] = None
    reason: Optional[str] = None


class PlayerAction(BaseModel):
    player: str


class DrawResponse(BaseModel):
    player: str
    accept: bool


@board_router.get("/board", name="board")
async def board_redirect(request: Request):
    board_id = str(uuid.uuid4())
    return RedirectResponse(request.url_for("board_page", board_id=board_id))


@board_router.get("/board/{board_id}", response_class=HTMLResponse, name="board_page")
async def board_page(request: Request, board_id: str):
    if request.query_params:
        url = request.url_for("board_page", board_id=board_id)
        return RedirectResponse(url, status_code=302)
    
    session_user = request.session.get("user_id")
    if session_user and await board_exists(board_id):
        await assign_user_board(str(session_user), board_id)
    players = await get_board_players(board_id)
    color = ""
    if session_user and players:
        for c, uid in players.items():
            if uid == str(session_user):
                color = c
                break
    return templates.TemplateResponse(
        "board.html",
        {
            "request": request,
            "board_id": board_id,
            "player_color": color,
            "api_base": "/api",
        },
    )


@board_router.get("/api/board/{board_id}", response_model=BoardState)
async def api_get_board(board_id: str):
    players_raw = await get_board_players(board_id)
    if not players_raw:
        raise HTTPException(status_code=404)
    board = await get_board_state(board_id)
    history = await get_history(board_id)
    timers = await get_current_timers(board_id)
    players = {}
    for color, uid in players_raw.items():
        login = await get_user_login(int(uid))
        players[color] = login or str(uid)
    return BoardState(board=board, history=history, timers=timers, players=players)


@board_router.get("/api/timers/{board_id}", response_model=Timers)
async def api_get_timers(board_id: str):
    if not await board_exists(board_id):
        raise HTTPException(status_code=404)
    timers = await get_current_timers(board_id)
    if timers is None:
        raise HTTPException(status_code=404)
    return timers


@board_router.get("/api/moves/{board_id}", response_model=List[Point])
async def api_get_moves(board_id: str, row: int, col: int, player: str):
    if not await board_exists(board_id):
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


@board_router.get("/api/captures/{board_id}", response_model=List[Point])
async def api_get_captures(board_id: str, row: int, col: int, player: str):
    if not await board_exists(board_id):
        raise HTTPException(status_code=404)
    board = await get_board_state(board_id, create=False)
    return piece_capture_moves(board, (row, col), player)


@board_router.post("/api/move/{board_id}", response_model=MoveResult)
async def api_make_move(request: Request, board_id: str, req: MoveRequest):
    user_id = request.session.get("user_id")
    if user_id is None:
        raise HTTPException(status_code=401)
    if not await board_exists(board_id):
        raise HTTPException(status_code=404)
    players = await get_board_players(board_id)
    if players and players.get(req.player) != str(user_id):
        raise HTTPException(status_code=403, detail="Invalid player")
    board = await get_board_state(board_id, create=False)

    try:
        new_board = await validate_move(board, req.start, req.end, req.player)
    except ValueError as e:
        logger.error(
            "Invalid move on board %s by %s: %s -> %s (%s)",
            board_id,
            req.player,
            req.start,
            req.end,
            e,
        )
        raise HTTPException(status_code=400, detail=str(e))

    await save_board_state(board_id, new_board)
    move_notation = (
        f"{chr(req.start[1] + 65)}{8 - req.start[0]}"
        f"->{chr(req.end[1] + 65)}{8 - req.end[0]}"
    )
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

    reason = None
    if timers[req.player] <= 0:
        status = "black_win" if req.player == "white" else "white_win"
        reason = "timeout"
    else:
        status = game_status(new_board)
        if status == "white_win":
            reason = determine_win_reason(new_board, "white")
        elif status == "black_win":
            reason = determine_win_reason(new_board, "black")
        elif status == "draw":
            reason = "stalemate"

    rating_change = None
    if status:
        players = await get_board_players(board_id)
        history = await get_history(board_id)
        if players:
            white_id = int(players.get("white"))
            black_id = int(players.get("black"))
            white_stats = await get_user_stats(white_id)
            black_stats = await get_user_stats(black_id)
            rating_change = {}
            if status == "white_win":
                rating_change["white"] = await record_game_result(
                    white_id, "win", black_stats["elo"]
                )
                rating_change["black"] = await record_game_result(
                    black_id, "loss", white_stats["elo"]
                )
            elif status == "black_win":
                rating_change["white"] = await record_game_result(
                    white_id, "loss", black_stats["elo"]
                )
                rating_change["black"] = await record_game_result(
                    black_id, "win", white_stats["elo"]
                )
            else:
                rating_change["white"] = await record_game_result(
                    white_id, "draw", black_stats["elo"]
                )
                rating_change["black"] = await record_game_result(
                    black_id, "draw", white_stats["elo"]
                )
            result_map = {
                "white_win": {"white": "win", "black": "loss"},
                "black_win": {"white": "loss", "black": "win"},
                "draw": {"white": "draw", "black": "draw"},
            }
            await save_recorded_game(
                board_id,
                white_id,
                black_id,
                history,
                status,
                mode="multiplayer",
                ranked=True,
            )
            for color, uid in players.items():
                await record_game(
                    int(uid),
                    "ranked",
                    result_map[status][color],
                    rating_change.get(color),
                    game_id=board_id,
                )
        current_timers = await get_current_timers(board_id, create=False)
        await cleanup_board(board_id)
        await clear_lobby_board(board_id)

    else:
        history = await get_history(board_id)
        current_timers = await get_current_timers(board_id)
    result = MoveResult(
        board=new_board,
        status=status,
        history=history,
        timers=current_timers,
        rating_change=rating_change,
        reason=reason,
    )
    await board_manager.broadcast(board_id, result.json())
    return result


@board_router.get("/api/snapshot/{board_id}/{index}", response_model=Board)
async def api_board_snapshot(board_id: str, index: int):
    if not await board_exists(board_id):
        raise HTTPException(status_code=404)
    board = await get_board_state_at(board_id, index)
    return board


@board_router.post("/api/resign/{board_id}", response_model=MoveResult)
async def api_resign(request: Request, board_id: str, action: PlayerAction):
    user_id = request.session.get("user_id")
    if user_id is None:
        raise HTTPException(status_code=401)
    if not await board_exists(board_id):
        raise HTTPException(status_code=404)
    players = await get_board_players(board_id)
    if players and players.get(action.player) != str(user_id):
        raise HTTPException(status_code=403, detail="Invalid player")
    board = await get_board_state(board_id, create=False)
    status = "black_win" if action.player == "white" else "white_win"
    players = await get_board_players(board_id)
    if players:
        white_id = int(players.get("white"))
        black_id = int(players.get("black"))
        white_stats = await get_user_stats(white_id)
        black_stats = await get_user_stats(black_id)
        rating_change = {}
        if status == "white_win":
            rating_change["white"] = await record_game_result(
                white_id, "win", black_stats["elo"]
            )
            rating_change["black"] = await record_game_result(
                black_id, "loss", white_stats["elo"]
            )
        else:
            rating_change["white"] = await record_game_result(
                white_id, "loss", black_stats["elo"]
            )
            rating_change["black"] = await record_game_result(
                black_id, "win", white_stats["elo"]
            )
        result_map = {
            "white_win": {"white": "win", "black": "loss"},
            "black_win": {"white": "loss", "black": "win"},
        }
        history = await get_history(board_id)
        await save_recorded_game(
            board_id,
            white_id,
            black_id,
            history,
            status,
            mode="multiplayer",
            ranked=True,
        )
        for color, uid in players.items():
            await record_game(
                int(uid),
                "ranked",
                result_map[status][color],
                rating_change.get(color),
                game_id=board_id,
            )
    timers = await get_current_timers(board_id, create=False)
    await cleanup_board(board_id)
    await clear_lobby_board(board_id)
    result = MoveResult(
        board=board,
        status=status,
        history=history,
        timers=timers,
        rating_change=rating_change,
        reason="resign",
    )
    await board_manager.broadcast(board_id, result.json())
    return result


@board_router.post("/api/draw_offer/{board_id}")
async def api_draw_offer(request: Request, board_id: str, action: PlayerAction):
    user_id = request.session.get("user_id")
    if user_id is None:
        raise HTTPException(status_code=401)
    if not await board_exists(board_id):
        raise HTTPException(status_code=404)
    players = await get_board_players(board_id)
    if players and players.get(action.player) != str(user_id):
        raise HTTPException(status_code=403, detail="Invalid player")
    await set_draw_offer(board_id, action.player)
    await board_manager.broadcast(
        board_id, json.dumps({"type": "draw_offer", "from": action.player})
    )
    return {"status": "ok"}


@board_router.post("/api/draw_response/{board_id}")
async def api_draw_response(request: Request, board_id: str, resp: DrawResponse):
    user_id = request.session.get("user_id")
    if user_id is None:
        raise HTTPException(status_code=401)
    if not await board_exists(board_id):
        raise HTTPException(status_code=404)
    players = await get_board_players(board_id)
    if players and players.get(resp.player) != str(user_id):
        raise HTTPException(status_code=403, detail="Invalid player")
    offer = await get_draw_offer(board_id)
    await clear_draw_offer(board_id)
    if resp.accept and offer and resp.player != offer:
        board = await get_board_state(board_id, create=False)
        players = await get_board_players(board_id)
        rating_change = None
        if players:
            white_id = int(players.get("white"))
            black_id = int(players.get("black"))
            white_stats = await get_user_stats(white_id)
            black_stats = await get_user_stats(black_id)
            rating_change = {
                "white": await record_game_result(white_id, "draw", black_stats["elo"]),
                "black": await record_game_result(black_id, "draw", white_stats["elo"]),
            }
            history = await get_history(board_id)
            await save_recorded_game(
                board_id,
                white_id,
                black_id,
                history,
                "draw",
                mode="multiplayer",
                ranked=True,
            )
            for color, uid in players.items():
                await record_game(int(uid), "ranked", "draw", rating_change.get(color), game_id=board_id)
        timers = await get_current_timers(board_id, create=False)
        await cleanup_board(board_id)
        await clear_lobby_board(board_id)
        result = MoveResult(
            board=board,
            status="draw",
            history=history,
            timers=timers,
            rating_change=rating_change,
            reason="agreement",
        )
        await board_manager.broadcast(board_id, result.json())
        return result
    else:
        await board_manager.broadcast(board_id, json.dumps({"type": "draw_declined"}))
        return {"status": "declined"}


@board_router.post("/api/check_timeout/{board_id}", response_model=MoveResult)
async def api_check_timeout(board_id: str):
    if not await board_exists(board_id):
        raise HTTPException(status_code=404)
    board = await get_board_state(board_id, create=False)
    timers = await get_current_timers(board_id, create=False)
    history = await get_history(board_id)
    active = timers["turn"]
    status = None
    reason = None
    if timers[active] <= 0:
        status = "black_win" if active == "white" else "white_win"
        reason = "timeout"
    if not status:
        return MoveResult(board=board, status=None, history=history, timers=timers, reason=None)

    players = await get_board_players(board_id)
    rating_change = None
    if players:
        white_id = int(players.get("white"))
        black_id = int(players.get("black"))
        white_stats = await get_user_stats(white_id)
        black_stats = await get_user_stats(black_id)
        rating_change = {}
        if status == "white_win":
            rating_change["white"] = await record_game_result(
                white_id, "win", black_stats["elo"]
            )
            rating_change["black"] = await record_game_result(
                black_id, "loss", white_stats["elo"]
            )
        else:
            rating_change["white"] = await record_game_result(
                white_id, "loss", black_stats["elo"]
            )
            rating_change["black"] = await record_game_result(
                black_id, "win", white_stats["elo"]
            )
        result_map = {
            "white_win": {"white": "win", "black": "loss"},
            "black_win": {"white": "loss", "black": "win"},
        }
        await save_recorded_game(
            board_id,
            white_id,
            black_id,
            history,
            status,
            mode="multiplayer",
            ranked=True,
        )
        for color, uid in players.items():
            await record_game(
                int(uid),
                "ranked",
                result_map[status][color],
                rating_change.get(color),
                game_id=board_id,
            )

    await cleanup_board(board_id)
    await clear_lobby_board(board_id)
    result = MoveResult(
        board=board,
        status=status,
        history=history,
        timers=timers,
        rating_change=rating_change,
        reason=reason,
    )
    await board_manager.broadcast(board_id, result.json())
    return result

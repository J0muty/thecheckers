import uuid
import logging
import time
import os
import orjson
import json
from collections.abc import Collection
from functools import wraps
from fastapi import Request, APIRouter, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Tuple
from src.app.routers.ws_router import board_manager, notify_manager
from src.settings.settings import templates
from src.app.game.draw_logic import (
    initial_draw_state,
    rebuild_draw_state_from_history,
    update_draw_state,
)
from src.base.redis import (
    board_exists,
    get_board_state,
    save_board_state,
    assign_user_board,
    set_board_players,
    get_history,
    append_history,
    get_current_timers,
    apply_move_timer,
    apply_same_turn_timer,
    freeze_timers,
    get_board_state_at,
    get_board_players,
    expire_board,
    DEFAULT_TIME,
    redis_client,
    REDIS_KEY_PREFIX,
    PLAYERS_KEY,
    set_draw_offer,
    get_draw_offer,
    clear_draw_offer,
    add_rematch_invite,
    remove_rematch_invite,
    get_board_rematch_invites,
    get_chain_state,
    save_chain_state,
    clear_chain_state,
    get_draw_state,
    save_draw_state,
    clear_draw_state,
    get_user_move_input_mode,
)
from src.base.lobby_redis import clear_lobby_board
from src.app.game.game_logic import (
    apply_move,
    format_move,
    legal_piece_moves,
    piece_capture_moves,
    game_status,
    man_moves,
    king_moves,
    opponent,
    owner,
    create_initial_board
)
from src.base.postgres import (
    record_game_result,
    get_user_stats,
    get_user_login,
    record_game,
    save_recorded_game,
)
from src.app.achievements.rating import check_rating_achievements
from src.app.utils.guest import is_guest, get_display_name
from logging.handlers import QueueHandler, QueueListener
import queue
os.makedirs("src/logs", exist_ok=True)
logger = logging.getLogger("board_router")
logger.setLevel(logging.INFO)
fh = logging.FileHandler("src/logs/board_router.log", encoding="utf-8")
fmt = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
fh.setFormatter(fmt)
if not logger.handlers:
    logger.addHandler(fh)
log_queue = queue.Queue(-1)
qhandler = QueueHandler(log_queue)
if not any(isinstance(handler, QueueHandler) for handler in logger.handlers):
    logger.addHandler(qhandler)
    listener = QueueListener(log_queue, fh)
    listener.start()

PROFILE_ROUTER = os.getenv("CHECKERS_PROFILE_ROUTER") == "1"
ROUTER_SLOW_LOG_MS = float(os.getenv("CHECKERS_ROUTER_LOG_SLOW_MS", "15"))
PROFILE_FRONTEND = os.getenv("CHECKERS_PROFILE_FRONTEND") == "1"
FRONTEND_SLOW_LOG_MS = float(os.getenv("CHECKERS_FRONTEND_LOG_SLOW_MS", "25"))

def log_time(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = await func(*args, **kwargs)
        duration = (time.perf_counter() - start) * 1000
        if PROFILE_ROUTER or duration >= ROUTER_SLOW_LOG_MS:
            logger.info(f"Функция {func.__name__} выполнилась за {duration:.2f} мс")
        return result
    return wrapper

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
            moves = man_moves(board, (r, c), opponent) if p.islower() else king_moves(board, (r, c), opponent)
            if moves:
                can_move = True
                break
    if not has_piece:
        return "no_pieces"
    if not can_move:
        return "no_moves"
    return "unknown"

class FrontendLog(BaseModel):
    function: str
    duration: float

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
    rating_change: Optional[dict[str, int]] = None
    reason: Optional[str] = None
    forced_piece: Optional[Point] = None
    forced_moves: List[Point] = Field(default_factory=list)

class PlayerAction(BaseModel):
    player: str

class DrawResponse(BaseModel):
    player: str
    accept: bool


def _blocked_positions(chain_state: dict | None) -> list[Point]:
    if not chain_state:
        return []
    return [tuple(pos) for pos in chain_state.get("captured_positions", [])]


def _forced_piece(chain_state: dict | None) -> Point | None:
    if not chain_state or "piece" not in chain_state:
        return None
    piece = chain_state.get("piece")
    return tuple(piece) if piece else None


def _forced_moves_payload(board: Board, chain_state: dict | None) -> tuple[Point | None, list[Point]]:
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

@board_router.post("/api/frontend-log")
async def api_frontend_log(log: FrontendLog):
    if not PROFILE_FRONTEND or log.duration < FRONTEND_SLOW_LOG_MS:
        return JSONResponse({"status": "ignored"})
    logger.info(f"Frontend: {log.function} выполнилась за {log.duration:.2f} ms")
    return JSONResponse({"status": "ok"})

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
    ranked_game = bool(
        players
        and str(players.get("white", "")).isdigit()
        and str(players.get("black", "")).isdigit()
    )
    move_input_mode = "click"
    if session_user and not is_guest(session_user):
        move_input_mode = await get_user_move_input_mode(session_user)
    return templates.TemplateResponse(
        "board.html",
        {
            "request": request,
            "board_id": board_id,
            "player_color": color,
            "api_base": "/api",
            "ranked_game": ranked_game,
            "move_input_mode": move_input_mode,
        },
    )

@board_router.get("/api/board/{board_id}", response_model=BoardState)
async def api_get_board(board_id: str):
    players_raw = await get_board_players(board_id)
    if not players_raw:
        raise HTTPException(status_code=404)
    board_key = f"{REDIS_KEY_PREFIX}:{board_id}:state"
    timer_key = f"{REDIS_KEY_PREFIX}:{board_id}:timer"
    history_key = f"{REDIS_KEY_PREFIX}:{board_id}:history"
    chain_key = f"{REDIS_KEY_PREFIX}:{board_id}:chain"
    pipe = redis_client.pipeline()
    pipe.get(board_key)
    pipe.get(timer_key)
    pipe.lrange(history_key, 0, -1)
    pipe.get(chain_key)
    board_raw, timer_raw, history_list, chain_raw = await pipe.execute()
    board = orjson.loads(board_raw.encode()) if board_raw else create_initial_board()
    if not board_raw:
        await redis_client.set(board_key, orjson.dumps(board).decode())
        await save_draw_state(board_id, initial_draw_state(board))
    timers_view = None
    if timer_raw:
        timers = orjson.loads(timer_raw.encode())
        turn = timers.get("turn")
        if turn in ("white", "black"):
            now = time.time()
            elapsed = now - timers["last_ts"]
            timers[turn] = max(0, timers[turn] - elapsed)
        timers.pop("last_ts", None)
        timers_view = timers
    else:
        now = time.time()
        timers_full = {"white": DEFAULT_TIME, "black": DEFAULT_TIME, "turn": "white", "last_ts": now}
        timers_view = {"white": DEFAULT_TIME, "black": DEFAULT_TIME, "turn": "white"}
        await redis_client.set(timer_key, orjson.dumps(timers_full).decode())
    chain_state = orjson.loads(chain_raw.encode()) if chain_raw else None
    forced_piece, forced_moves = _forced_moves_payload(board, chain_state)
    players = {}
    for color, uid in players_raw.items():
        players[color] = await get_display_name(uid)
    return BoardState(
        board=board,
        history=history_list,
        timers=timers_view,
        players=players,
        forced_piece=forced_piece,
        forced_moves=forced_moves,
    )

@board_router.get("/api/timers/{board_id}", response_model=Timers)
async def api_get_timers(board_id: str):
    if not await board_exists(board_id):
        raise HTTPException(status_code=404)
    timers = await get_current_timers(board_id)
    if timers is None:
        raise HTTPException(status_code=404)
    return timers

@board_router.get("/api/moves/{board_id}", response_model=List[Point])
@log_time
async def api_get_moves(board_id: str, row: int, col: int, player: str):
    board = await get_board_state(board_id, create=False)
    if board is None:
        raise HTTPException(status_code=404)
    timers = await get_current_timers(board_id, create=False)
    if timers and timers.get("turn") != player:
        return []
    chain_state = await get_chain_state(board_id)
    forced_piece = _forced_piece(chain_state)
    blocked_positions = _blocked_positions(chain_state)
    p = board[row][col] if 0 <= row < 8 and 0 <= col < 8 else None
    if not p or owner(p) != player:
        return []
    return legal_piece_moves(
        board,
        (row, col),
        player,
        blocked_positions=blocked_positions,
        forced_start=forced_piece,
    )

@board_router.get("/api/captures/{board_id}", response_model=List[Point])
async def api_get_captures(board_id: str, row: int, col: int, player: str):
    board = await get_board_state(board_id, create=False)
    if board is None:
        raise HTTPException(status_code=404)
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

@board_router.post("/api/move/{board_id}", response_model=MoveResult)
@log_time
async def api_make_move(request: Request, board_id: str, req: MoveRequest):
    user_id = request.session.get("user_id")
    if user_id is None:
        raise HTTPException(status_code=401)
    board_key = f"{REDIS_KEY_PREFIX}:{board_id}:state"
    timer_key = f"{REDIS_KEY_PREFIX}:{board_id}:timer"
    history_key = f"{REDIS_KEY_PREFIX}:{board_id}:history"
    players_key = f"{REDIS_KEY_PREFIX}:{board_id}:{PLAYERS_KEY}"
    chain_key = f"{REDIS_KEY_PREFIX}:{board_id}:chain"
    pipe = redis_client.pipeline()
    pipe.get(board_key)
    pipe.get(timer_key)
    pipe.get(players_key)
    pipe.lrange(history_key, 0, -1)
    pipe.get(chain_key)
    board_raw, timer_raw, players_raw, history_list, chain_raw = await pipe.execute()
    if not board_raw:
        raise HTTPException(status_code=404)
    board = orjson.loads(board_raw.encode())
    players_map = orjson.loads(players_raw.encode()) if players_raw else None
    if players_map is None:
        raise HTTPException(status_code=404)
    if players_map.get(req.player) != str(user_id):
        raise HTTPException(status_code=403, detail="Invalid player")
    timers = orjson.loads(timer_raw.encode()) if timer_raw else None
    if timers and timers.get("turn") not in ("white", "black"):
        raise HTTPException(status_code=400, detail="Game finished")
    if timers and timers.get("turn") != req.player:
        raise HTTPException(status_code=409, detail="Not your turn")
    if len(history_list) != req.history_len:
        raise HTTPException(status_code=409, detail="Out of sync")

    draw_state = await _load_draw_state(board_id, history_list)
    chain_state = orjson.loads(chain_raw.encode()) if chain_raw else None
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
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    move_notation = format_move(req.start, req.end)
    next_chain_state = None
    forced_piece = None
    forced_moves: list[Point] = []
    more_captures = False
    if captured is not None:
        next_blocked = blocked_positions + [captured]
        forced_moves = piece_capture_moves(
            new_board,
            req.end,
            req.player,
            blocked_positions=next_blocked,
        )
        if forced_moves:
            more_captures = True
            forced_piece = req.end
            next_chain_state = {
                "player": req.player,
                "piece": list(req.end),
                "captured_positions": [list(pos) for pos in next_blocked],
                "turn_start_board": turn_start_board,
                "start_piece_is_king": turn_piece_was_king,
            }
    if timers is None:
        timers = {"white": DEFAULT_TIME, "black": DEFAULT_TIME, "turn": "white", "last_ts": time.time()}
    now_time = time.time()
    elapsed = now_time - timers["last_ts"]
    timers[req.player] = max(0, timers[req.player] - elapsed)
    new_turn = req.player if more_captures else opponent(req.player)
    timers["turn"] = new_turn
    timers["last_ts"] = now_time

    pipe2 = redis_client.pipeline(transaction=True)
    pipe2.set(board_key, orjson.dumps(new_board).decode())
    pipe2.rpush(history_key, move_notation)
    pipe2.set(timer_key, orjson.dumps(timers).decode())
    if next_chain_state is None:
        pipe2.delete(chain_key)
    else:
        pipe2.set(chain_key, orjson.dumps(next_chain_state).decode())
    await pipe2.execute()

    history_list.append(move_notation)
    status = None if more_captures else game_status(new_board)
    if not more_captures and status is None:
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
    reason = determine_win_reason(new_board, status.split("_")[0]) if status in ("white_win", "black_win") else None
    timers_out = timers.copy()
    timers_out.pop("last_ts", None)
    rating_change = None

    if status:
        players = await get_board_players(board_id)
        if players and players.get("white", "").isdigit() and players.get("black", "").isdigit():
            white_id = int(players["white"])
            black_id = int(players["black"])
            saved = await save_recorded_game(board_id, white_id, black_id, history_list, status, mode="multiplayer", ranked=True)
            if saved:
                white_stats = await get_user_stats(white_id)
                black_stats = await get_user_stats(black_id)
                rating_change = {}
                if status == "white_win":
                    rating_change["white"] = await record_game_result(white_id, "win", black_stats["elo"])
                    rating_change["black"] = await record_game_result(black_id, "loss", white_stats["elo"])
                elif status == "black_win":
                    rating_change["white"] = await record_game_result(white_id, "loss", black_stats["elo"])
                    rating_change["black"] = await record_game_result(black_id, "win", white_stats["elo"])
                else:
                    rating_change["white"] = await record_game_result(white_id, "draw", black_stats["elo"])
                    rating_change["black"] = await record_game_result(black_id, "draw", white_stats["elo"])
                result_map = {
                    "white_win": {"white": "win", "black": "loss"},
                    "black_win": {"white": "loss", "black": "win"},
                    "draw": {"white": "draw", "black": "draw"},
                }
                for color, uid in players.items():
                    await record_game(int(uid), "ranked", result_map[status][color], rating_change.get(color), game_id=board_id)
                await check_rating_achievements(white_id)
                await check_rating_achievements(black_id)
        await freeze_timers(board_id)
        timers_out = await get_current_timers(board_id, create=False)
        if timers_out and "last_ts" in timers_out:
            timers_out = {k: v for k, v in timers_out.items() if k != "last_ts"}
        await clear_chain_state(board_id)
        await clear_draw_state(board_id)
        await expire_board(board_id, delay=600)
        await clear_lobby_board(board_id)
        forced_piece = None
        forced_moves = []

    result = MoveResult(
        board=new_board,
        status=status,
        history=history_list,
        timers=timers_out,
        rating_change=rating_change,
        reason=reason,
        forced_piece=forced_piece,
        forced_moves=forced_moves,
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
    timers_check = await get_current_timers(board_id, create=False)
    if timers_check and timers_check.get("turn") not in ("white", "black"):
        raise HTTPException(status_code=400, detail="Game finished")
    board = await get_board_state(board_id, create=False)
    history = await get_history(board_id)
    rating_change = None
    status = "black_win" if action.player == "white" else "white_win"
    players = await get_board_players(board_id)
    if players and players.get("white").isdigit() and players.get("black").isdigit():
        white_id = int(players.get("white"))
        black_id = int(players.get("black"))
        saved = await save_recorded_game(board_id, white_id, black_id, history, status, mode="multiplayer", ranked=True)
        if saved:
            white_stats = await get_user_stats(white_id)
            black_stats = await get_user_stats(black_id)
            rating_change = {}
            if status == "white_win":
                rating_change["white"] = await record_game_result(white_id, "win", black_stats["elo"])
                rating_change["black"] = await record_game_result(black_id, "loss", white_stats["elo"])
            else:
                rating_change["white"] = await record_game_result(white_id, "loss", black_stats["elo"])
                rating_change["black"] = await record_game_result(black_id, "win", white_stats["elo"])
            result_map = {
                "white_win": {"white": "win", "black": "loss"},
                "black_win": {"white": "loss", "black": "win"},
            }
            for color, uid in players.items():
                await record_game(int(uid), "ranked", result_map[status][color], rating_change.get(color), game_id=board_id)
            await check_rating_achievements(white_id)
            await check_rating_achievements(black_id)
    timers = await freeze_timers(board_id)
    await clear_draw_state(board_id)
    await expire_board(board_id, delay=600)
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
    timers_check = await get_current_timers(board_id, create=False)
    if timers_check and timers_check.get("turn") not in ("white", "black"):
        raise HTTPException(status_code=400, detail="Game finished")
    await set_draw_offer(board_id, action.player)
    await board_manager.broadcast(board_id, json.dumps({"type": "draw_offer", "from": action.player}))
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
    timers_check = await get_current_timers(board_id, create=False)
    if timers_check and timers_check.get("turn") not in ("white", "black"):
        raise HTTPException(status_code=400, detail="Game finished")
    offer = await get_draw_offer(board_id)
    await clear_draw_offer(board_id)
    if resp.accept and offer and resp.player != offer:
        board = await get_board_state(board_id, create=False)
        history = await get_history(board_id)
        players = await get_board_players(board_id)
        rating_change = None
        if players and players.get("white").isdigit() and players.get("black").isdigit():
            white_id = int(players.get("white"))
            black_id = int(players.get("black"))
            saved = await save_recorded_game(board_id, white_id, black_id, history, "draw", mode="multiplayer", ranked=True)
            if saved:
                white_stats = await get_user_stats(white_id)
                black_stats = await get_user_stats(black_id)
                rating_change = {
                    "white": await record_game_result(white_id, "draw", black_stats["elo"]),
                    "black": await record_game_result(black_id, "draw", white_stats["elo"]),
                }
                for color, uid in players.items():
                    await record_game(int(uid), "ranked", "draw", rating_change.get(color), game_id=board_id)
                await check_rating_achievements(white_id)
                await check_rating_achievements(black_id)
        timers = await freeze_timers(board_id)
        await clear_draw_state(board_id)
        await expire_board(board_id, delay=600)
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
    active = timers.get("turn")
    if active not in ("white", "black"):
        return MoveResult(board=board, status=None, history=history, timers=timers, reason=None)
    status = None
    reason = None
    if timers[active] <= 0:
        status = "black_win" if active == "white" else "white_win"
        reason = "timeout"
    if not status:
        return MoveResult(board=board, status=None, history=history, timers=timers, reason=None)
    players = await get_board_players(board_id)
    rating_change = None
    if players and players.get("white").isdigit() and players.get("black").isdigit():
        white_id = int(players.get("white"))
        black_id = int(players.get("black"))
        saved = await save_recorded_game(board_id, white_id, black_id, history, status, mode="multiplayer", ranked=True)
        if saved:
            white_stats = await get_user_stats(white_id)
            black_stats = await get_user_stats(black_id)
            rating_change = {}
            if status == "white_win":
                rating_change["white"] = await record_game_result(white_id, "win", black_stats["elo"])
                rating_change["black"] = await record_game_result(black_id, "loss", white_stats["elo"])
            else:
                rating_change["white"] = await record_game_result(white_id, "loss", black_stats["elo"])
                rating_change["black"] = await record_game_result(black_id, "win", white_stats["elo"])
            result_map = {
                "white_win": {"white": "win", "black": "loss"},
                "black_win": {"white": "loss", "black": "win"},
            }
            for color, uid in players.items():
                await record_game(int(uid), "ranked", result_map[status][color], rating_change.get(color), game_id=board_id)
            await check_rating_achievements(white_id)
            await check_rating_achievements(black_id)
    timers = await freeze_timers(board_id)
    await clear_draw_state(board_id)
    await expire_board(board_id, delay=600)
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

@board_router.post("/api/rematch_request/{board_id}")
async def api_rematch_request(request: Request, board_id: str):
    user_id = request.session.get("user_id")
    if user_id is None:
        raise HTTPException(status_code=401)
    players = await get_board_players(board_id)
    if not players or str(user_id) not in players.values():
        raise HTTPException(status_code=404)
    opponent_id = None
    my_color = None
    for color, uid in players.items():
        if uid == str(user_id):
            my_color = color
        else:
            opponent_id = uid
    if not opponent_id:
        raise HTTPException(status_code=400)
    await add_rematch_invite(board_id, opponent_id, str(user_id))
    msg = json.dumps({"type": "rematch_offer", "from": my_color})
    await board_manager.broadcast(board_id, msg)
    await notify_manager.broadcast(opponent_id, json.dumps({"type": "invite"}))
    return JSONResponse({"status": "ok"})

@board_router.post("/api/rematch_response/{board_id}")
async def api_rematch_response(request: Request, board_id: str, action: str):
    user_id = request.session.get("user_id")
    if user_id is None:
        raise HTTPException(status_code=401)
    players = await get_board_players(board_id)
    if not players:
        raise HTTPException(status_code=404)
    invites = await get_board_rematch_invites(board_id)
    sender_id = invites.get(str(user_id))
    if not sender_id:
        raise HTTPException(status_code=404)
    await remove_rematch_invite(board_id, str(user_id))
    if action == "accept":
        new_board_id = str(uuid.uuid4())
        await set_board_players(new_board_id, players)
        for uid in players.values():
            await assign_user_board(uid, new_board_id)
        await board_manager.broadcast(
            board_id, json.dumps({"type": "rematch_start", "board_id": new_board_id})
        )
        await notify_manager.broadcast(
            sender_id, json.dumps({"type": "rematch_start", "board_id": new_board_id})
        )
        await notify_manager.broadcast(
            str(user_id), json.dumps({"type": "rematch_start", "board_id": new_board_id})
        )
        return JSONResponse({"board_id": new_board_id})
    else:
        await board_manager.broadcast(board_id, json.dumps({"type": "rematch_decline"}))
        if str(user_id).isdigit():
            login = await get_user_login(int(user_id))
        else:
            login = str(user_id)
        await notify_manager.broadcast(
            sender_id,
            json.dumps({"type": "rematch_decline", "from_login": login or str(user_id)})
        )
        return JSONResponse({"status": "declined"})

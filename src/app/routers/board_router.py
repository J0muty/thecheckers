import uuid
import logging
import time
import os
import orjson
from functools import wraps
from fastapi import Request, APIRouter, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from pydantic import BaseModel
from typing import List, Optional, Tuple
from src.app.routers.ws_router import board_manager, notify_manager
from src.settings.settings import templates
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
)
from src.base.lobby_redis import clear_lobby_board
from src.app.game.game_logic import (
    validate_move,
    piece_capture_moves,
    game_status,
    man_moves,
    king_moves,
    owner,
    any_capture,
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
logger.addHandler(fh)
log_queue = queue.Queue(-1)
qhandler = QueueHandler(log_queue)
logger.addHandler(qhandler)
listener = QueueListener(log_queue, fh)
listener.start()

def log_time(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = await func(*args, **kwargs)
        duration = (time.perf_counter() - start) * 1000
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
    board_key = f"{REDIS_KEY_PREFIX}:{board_id}:state"
    timer_key = f"{REDIS_KEY_PREFIX}:{board_id}:timer"
    history_key = f"{REDIS_KEY_PREFIX}:{board_id}:history"
    pipe = redis_client.pipeline()
    pipe.get(board_key)
    pipe.get(timer_key)
    pipe.lrange(history_key, 0, -1)
    board_raw, timer_raw, history_list = await pipe.execute()
    board = orjson.loads(board_raw.encode()) if board_raw else create_initial_board()
    if not board_raw:
        await redis_client.set(board_key, orjson.dumps(board).decode())
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
    players = {}
    for color, uid in players_raw.items():
        players[color] = await get_display_name(uid)
    return BoardState(board=board, history=history_list, timers=timers_view, players=players)

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
    p = board[row][col] if 0 <= row < 8 and 0 <= col < 8 else None
    if not p or owner(p) != player:
        return []
    if any_capture(board, player):
        return piece_capture_moves(board, (row, col), player)
    return (man_moves(board, (row, col), player)
            if p.islower() else king_moves(board, (row, col), player))

@board_router.get("/api/captures/{board_id}", response_model=List[Point])
async def api_get_captures(board_id: str, row: int, col: int, player: str):
    board = await get_board_state(board_id, create=False)
    if board is None:
        raise HTTPException(status_code=404)
    return piece_capture_moves(board, (row, col), player)

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
    pipe = redis_client.pipeline()
    pipe.get(board_key)
    pipe.get(timer_key)
    pipe.get(players_key)
    board_raw, timer_raw, players_raw = await pipe.execute()
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
    new_board = validate_move(board, req.start, req.end, req.player)
    move_notation = (
        f"{chr(req.start[1] + 65)}{8 - req.start[0]}"
        f"->{chr(req.end[1] + 65)}{8 - req.end[0]}"
    )
    dr = abs(req.end[0] - req.start[0])
    dc = abs(req.end[1] - req.start[1])
    is_capture = dr > 1 or dc > 1
    more_captures = bool(piece_capture_moves(new_board, req.end, req.player)) if is_capture else False
    if timers is None:
        timers = {"white": DEFAULT_TIME, "black": DEFAULT_TIME, "turn": "white", "last_ts": time.time()}
    now_time = time.time()
    elapsed = now_time - timers["last_ts"]
    timers[req.player] = max(0, timers[req.player] - elapsed)
    new_turn = req.player if (is_capture and more_captures) else ("black" if req.player == "white" else "white")
    timers["turn"] = new_turn
    timers["last_ts"] = now_time
    pipe2 = redis_client.pipeline(transaction=True)
    pipe2.set(board_key, orjson.dumps(new_board).decode())
    pipe2.rpush(history_key, move_notation)
    pipe2.set(timer_key, orjson.dumps(timers).decode())
    pipe2.lrange(history_key, 0, -1)
    _, _, _, history_list = await pipe2.execute()
    status = game_status(new_board)
    reason = determine_win_reason(new_board, status.split("_")[0]) if status in ("white_win", "black_win") else ("stalemate" if status=="draw" else None)
    timers_out = timers.copy()
    timers_out.pop("last_ts", None)
    result = MoveResult(board=new_board, status=status, history=history_list, timers=timers_out, reason=reason)
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
    history = await get_history(board_id)
    rating_change = None
    status = "black_win" if action.player == "white" else "white_win"
    players = await get_board_players(board_id)
    if players and players.get("white").isdigit() and players.get("black").isdigit():
        white_id = int(players.get("white"))
        black_id = int(players.get("black"))
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
        await save_recorded_game(board_id, white_id, black_id, history, status, mode="multiplayer", ranked=True)
        for color, uid in players.items():
            await record_game(int(uid), "ranked", result_map[status][color], rating_change.get(color), game_id=board_id)
        await check_rating_achievements(white_id)
        await check_rating_achievements(black_id)
    timers = await freeze_timers(board_id)
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
            white_stats = await get_user_stats(white_id)
            black_stats = await get_user_stats(black_id)
            rating_change = {
                "white": await record_game_result(white_id, "draw", black_stats["elo"]),
                "black": await record_game_result(black_id, "draw", white_stats["elo"]),
            }
            await save_recorded_game(board_id, white_id, black_id, history, "draw", mode="multiplayer", ranked=True)
            for color, uid in players.items():
                await record_game(int(uid), "ranked", "draw", rating_change.get(color), game_id=board_id)
            await check_rating_achievements(white_id)
            await check_rating_achievements(black_id)
        timers = await freeze_timers(board_id)
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
    if players and players.get("white").isdigit() and players.get("black").isdigit():
        white_id = int(players.get("white"))
        black_id = int(players.get("black"))
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
        await save_recorded_game(board_id, white_id, black_id, history, status, mode="multiplayer", ranked=True)
        for color, uid in players.items():
            await record_game(int(uid), "ranked", result_map[status][color], rating_change.get(color), game_id=board_id)
        await check_rating_achievements(white_id)
        await check_rating_achievements(black_id)
    timers = await freeze_timers(board_id)
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

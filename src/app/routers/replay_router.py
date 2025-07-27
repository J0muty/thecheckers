from fastapi import Request, APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import List, Optional, Tuple

from src.settings.settings import templates
from src.base.postgres import get_recorded_game
from src.app.game.game_logic import validate_move, create_initial_board

Board = List[List[Optional[str]]]
Point = Tuple[int, int]

replay_router = APIRouter()


async def board_from_history(history: List[str], index: int) -> Board:
    if index > len(history):
        index = len(history)
    parsed: List[Tuple[Point, Point]] = []
    for mv in history[:index]:
        start_str, end_str = mv.split("->")
        start = (8 - int(start_str[1]), ord(start_str[0]) - 65)
        end = (8 - int(end_str[1]), ord(end_str[0]) - 65)
        parsed.append((start, end))

    board = await create_initial_board()
    player = "white"
    for i, (s, e) in enumerate(parsed):
        board = await validate_move(board, s, e, player)
        dr = abs(e[0] - s[0])
        dc = abs(e[1] - s[1])
        is_cap = dr > 1 or dc > 1
        next_chain = is_cap and i + 1 < len(parsed) and parsed[i + 1][0] == e
        if not next_chain:
            player = "black" if player == "white" else "white"
    return board


class ReplayState(BaseModel):
    board: Board
    history: List[str]
    players: Optional[dict[str, str]] = None


@replay_router.get("/replay/{game_id}", response_class=HTMLResponse, name="replay_page")
async def replay_page(request: Request, game_id: str):
    data = await get_recorded_game(game_id)
    if not data:
        raise HTTPException(status_code=404)
    color = ""
    user_id = request.session.get("user_id")
    if user_id:
        if data.get("white_id") == int(user_id):
            color = "white"
        elif data.get("black_id") == int(user_id):
            color = "black"
    return templates.TemplateResponse(
        "replay.html",
        {
            "request": request,
            "game_id": game_id,
            "players": data["players"],
            "player_color": color,
        },
    )


@replay_router.get("/api/replay/{game_id}", response_model=ReplayState)
async def api_replay(game_id: str):
    data = await get_recorded_game(game_id)
    if not data:
        raise HTTPException(status_code=404)
    board = await board_from_history(data["history"], len(data["history"]))
    return ReplayState(board=board, history=data["history"], players=data["players"])


@replay_router.get("/api/replay/{game_id}/{index}", response_model=Board)
async def api_replay_snapshot(game_id: str, index: int):
    data = await get_recorded_game(game_id)
    if not data:
        raise HTTPException(status_code=404)
    board = await board_from_history(data["history"], index)
    return board


# Additional routes for singleplayer and hotseat replays
@replay_router.get(
    "/single/replay/{game_id}", response_class=HTMLResponse, name="single_replay_page"
)
async def single_replay_page(request: Request, game_id: str):
    return await replay_page(request, game_id)


@replay_router.get(
    "/hotseat/replay/{game_id}", response_class=HTMLResponse, name="hotseat_replay_page"
)
async def hotseat_replay_page(request: Request, game_id: str):
    return await replay_page(request, game_id)


@replay_router.get("/api/single/replay/{game_id}", response_model=ReplayState)
async def api_single_replay(game_id: str):
    return await api_replay(game_id)


@replay_router.get("/api/hotseat/replay/{game_id}", response_model=ReplayState)
async def api_hotseat_replay(game_id: str):
    return await api_replay(game_id)


@replay_router.get("/api/single/replay/{game_id}/{index}", response_model=Board)
async def api_single_replay_snapshot(game_id: str, index: int):
    return await api_replay_snapshot(game_id, index)


@replay_router.get("/api/hotseat/replay/{game_id}/{index}", response_model=Board)
async def api_hotseat_replay_snapshot(game_id: str, index: int):
    return await api_replay_snapshot(game_id, index)

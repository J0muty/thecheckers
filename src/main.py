from fastapi import FastAPI
import uvicorn
import logging
from contextlib import asynccontextmanager
from starlette.middleware.sessions import SessionMiddleware
from src.app.middleware.session_validation import SessionValidationMiddleware
from src.app.routers import (
    pages_router,
    auth_router,
    profile_router,
    board_router,
    single_router,
    hotseat_router,
    replay_router,
    waiting_router,
    lobby_router,
    ws_router,
    chat_router,
)
from src.settings.settings import static_files
from src.base import postgres, redis

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - [%(filename)s] - %(message)s",
)

@asynccontextmanager
async def lifespan(_app: FastAPI):
    await postgres.init_db()
    await redis.check_redis_connection()
    yield

app = FastAPI(lifespan=lifespan)
app.add_middleware(SessionValidationMiddleware)
app.add_middleware(SessionMiddleware, secret_key="absolutesecretkey")
app.include_router(pages_router)
app.include_router(auth_router)
app.include_router(profile_router)
app.include_router(board_router)
app.include_router(hotseat_router)
app.include_router(replay_router)
app.include_router(waiting_router)
app.include_router(lobby_router)
app.include_router(ws_router)
app.include_router(single_router)
app.include_router(chat_router)

app.mount("/static", static_files, name="static")


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=1337, reload=True)

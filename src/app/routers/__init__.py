import src.app.routers.profile_router
from src.app.routers.pages_router import pages_router
from src.app.routers.auth_router import auth_router
from src.app.routers.profile_router import profile_router
from src.app.routers.board_router import board_router
from src.app.routers.waiting_router import waiting_router
from src.app.routers.lobby_router import lobby_router
from src.app.routers.ws_router import ws_router
from src.app.routers.chat_router import chat_router
from src.app.routers.single_router import single_router
from src.app.routers.hotseat_router import hotseat_router
from src.app.routers.replay_router import replay_router





# Список __all__ для явного указания экспортируемых имен
__all__ = [
    'pages_router',
    'auth_router',
    'profile_router',
    'board_router',
    'waiting_router',
    'ws_router',
    'chat_router',
    'single_router',
    'hotseat_router',
    'lobby_router',
    'replay_router',
]


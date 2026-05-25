from src.app.utils.guest import is_guest

USERS_ROOT = "users"
INDEX_ROOT = f"{USERS_ROOT}:_indexes"
QUEUE_ROOT = f"{USERS_ROOT}:_queue"
ORPHAN_USER = "_orphan"

REQUEST_TTL_SECONDS = 300
GUEST_FINISHED_GAME_TTL_SECONDS = 3600


def user_root(user_id: str | int) -> str:
    return f"{USERS_ROOT}:{user_id}"


def user_setting_key(user_id: str | int, setting: str) -> str:
    return f"{user_root(user_id)}:settings:{setting}"


def session_key(user_id: str | int, token: str) -> str:
    return f"{user_root(user_id)}:sessions:{token}"


def user_sessions_key(user_id: str | int) -> str:
    return f"{user_root(user_id)}:sessions:index"


def chat_messages_key(user1: int | str, user2: int | str) -> str:
    a, b = sorted([int(user1), int(user2)])
    return f"{user_root(a)}:chats:{b}:messages"


def user_chat_patterns(user_id: int | str) -> tuple[str, str]:
    uid = int(user_id)
    return (
        f"{user_root(uid)}:chats:*:messages",
        f"{USERS_ROOT}:*:chats:{uid}:messages",
    )


def single_owner_key(game_id: str) -> str:
    return f"{INDEX_ROOT}:games:singleplayers:{game_id}:owner"


def single_active_key(user_id: str | int) -> str:
    return f"{user_root(user_id)}:games:singleplayers:active"


def single_game_key(owner_id: str | int, game_id: str, field: str) -> str:
    return f"{user_root(owner_id)}:games:singleplayers:{game_id}:{field}"


def multiplayer_owner_key(board_id: str) -> str:
    return f"{INDEX_ROOT}:games:multiplayer:online:{board_id}:owner"


def multiplayer_active_key(user_id: str | int) -> str:
    return f"{user_root(user_id)}:games:multiplayer:online:active"


def multiplayer_ref_key(user_id: str | int, board_id: str) -> str:
    return f"{user_root(user_id)}:games:multiplayer:online:{board_id}:ref"


def multiplayer_game_key(owner_id: str | int, board_id: str, field: str) -> str:
    return f"{user_root(owner_id)}:games:multiplayer:online:{board_id}:{field}"


def multiplayer_game_pattern(owner_id: str | int, board_id: str) -> str:
    return f"{user_root(owner_id)}:games:multiplayer:online:{board_id}:*"


def rematch_user_invite_key(user_id: str | int, board_id: str) -> str:
    return f"{user_root(user_id)}:games:multiplayer:online:rematch:{board_id}"


def rematch_user_invites_pattern(user_id: str | int) -> str:
    return f"{user_root(user_id)}:games:multiplayer:online:rematch:*"


def rematch_board_invite_key(owner_id: str | int, board_id: str, user_id: str | int) -> str:
    return f"{multiplayer_game_key(owner_id, board_id, 'rematch')}:invites:{user_id}"


def rematch_board_invites_pattern(owner_id: str | int, board_id: str) -> str:
    return f"{multiplayer_game_key(owner_id, board_id, 'rematch')}:invites:*"


def rematch_state_key(owner_id: str | int, board_id: str) -> str:
    return f"{multiplayer_game_key(owner_id, board_id, 'rematch')}:state"


def hotseat_owner_key(game_id: str) -> str:
    return f"{INDEX_ROOT}:games:multiplayer:hotseat:{game_id}:owner"


def hotseat_active_key(user_id: str | int) -> str:
    return f"{user_root(user_id)}:games:multiplayer:hotseat:active"


def hotseat_game_key(owner_id: str | int, game_id: str, field: str) -> str:
    return f"{user_root(owner_id)}:games:multiplayer:hotseat:{game_id}:{field}"


def hotseat_game_pattern(owner_id: str | int, game_id: str) -> str:
    return f"{user_root(owner_id)}:games:multiplayer:hotseat:{game_id}:*"


def lobby_owner_key(lobby_id: str) -> str:
    return f"{INDEX_ROOT}:lobby:{lobby_id}:owner"


def lobby_active_key(user_id: str | int) -> str:
    return f"{user_root(user_id)}:lobby:active"


def lobby_key(owner_id: str | int, lobby_id: str, field: str) -> str:
    return f"{user_root(owner_id)}:lobby:{lobby_id}:{field}"


def lobby_pattern(owner_id: str | int, lobby_id: str) -> str:
    return f"{user_root(owner_id)}:lobby:{lobby_id}:*"


def lobby_user_invite_key(user_id: str | int, lobby_id: str) -> str:
    return f"{user_root(user_id)}:lobby:invites:{lobby_id}"


def lobby_user_invites_pattern(user_id: str | int) -> str:
    return f"{user_root(user_id)}:lobby:invites:*"


def lobby_invite_status_key(owner_id: str | int, lobby_id: str, user_id: str | int) -> str:
    return f"{lobby_key(owner_id, lobby_id, 'invites')}:{user_id}"


def lobby_invite_status_pattern(owner_id: str | int, lobby_id: str) -> str:
    return f"{lobby_key(owner_id, lobby_id, 'invites')}:*"


def waiting_queue_key(username: str) -> str:
    kind = "guests" if is_guest(username) else "registered"
    return f"{QUEUE_ROOT}:matchmaking:{kind}:waiting_user"


def waiting_since_key(username: str) -> str:
    return f"{user_root(username)}:games:multiplayer:online:waiting_since"

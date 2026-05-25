import json
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool
from sqlalchemy import text, select, func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import URL
from src.base.postgres_models import (
    Base,
    User,
    UserStats,
    Friend,
    FriendRequest,
    RecordedGame,
    GameHistory,
    Achievement,
    UserAchievement,
    UserWallet,
    UserCheckerSkin,
    UserSelectedCheckerSkin,
)
from src.app.achievements.data import ALL_ACHIEVEMENTS
from src.app.game.count_and_rang import update_elo, calculate_rank
from src.app.game.bot_profiles import PROFILE_ALIASES, normalize_difficulty
from src.app.shop.skins import (
    CHECKER_SKINS,
    CHECKER_SKIN_IDS,
    DEFAULT_CHECKER_SKIN_ID,
    STORE_ALL_ACCESS_LOGIN,
    checker_skin_by_id,
)
from src.app.utils.security import hash_password, verify_password
from src.settings.config import MOSCOW_TZ, db_user, db_password, db_host, db_port, db_name

async_session: None | async_sessionmaker[AsyncSession] = None

async def init_db():
    global async_session
    DATABASE_URL = URL.create(
        drivername="postgresql+asyncpg",
        username=db_user,
        password=db_password,
        host=db_host,
        port=db_port,
        database=db_name
    )
    engine = create_async_engine(
        DATABASE_URL,
        connect_args={"server_settings": {"timezone": "Europe/Moscow"}},
        future=True,
        echo=False,
        poolclass=NullPool,
    )
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS citext;"))
        await conn.run_sync(Base.metadata.create_all)

    await ensure_achievements(ALL_ACHIEVEMENTS)


def connect(method):
    async def wrapper(*args, **kwargs):
        async with async_session() as session:
            try:
                result = await method(*args, **kwargs, session=session)
                return result
            except ValueError as e:
                await session.rollback()
                raise e
            except Exception as e:
                await session.rollback()
                raise Exception(
                    f'Ошибка при работе с базой данных: {repr(e)} \nargs:\n{args}'
                )
    return wrapper

@connect
async def create_user(login: str, email: str, password: str, session: AsyncSession) -> User:
    login_norm = login.strip().lower()
    email_norm = email.strip().lower()

    login_q = await session.execute(select(User).where(User.login == login_norm))
    login_exists = login_q.scalar_one_or_none() is not None
    email_q = await session.execute(select(User).where(User.email == email_norm))
    email_exists = email_q.scalar_one_or_none() is not None

    if login_exists or email_exists:
        if login_exists and email_exists:
            raise ValueError("EXISTS_BOTH")
        if login_exists:
            raise ValueError("EXISTS_LOGIN")
        raise ValueError("EXISTS_EMAIL")

    pwd_hash = hash_password(password)
    user = User(login=login_norm, email=email_norm, password=pwd_hash)
    session.add(user)
    await session.commit()
    session.add(UserStats(user_id=user.id, elo=0, rank="Новичок"))
    await session.commit()
    return user

@connect
async def record_game_result(user_id: int, result: str, opponent_elo: int, session: AsyncSession) -> int:
    stats = await session.get(UserStats, user_id)
    if not stats:
        stats = UserStats(user_id=user_id, total_games=0, wins=0, draws=0, losses=0, elo=0, rank="Новичок")
        session.add(stats)
    old_elo = stats.elo or 0
    stats.total_games = (stats.total_games or 0) + 1
    if result == "win":
        stats.wins = (stats.wins or 0) + 1
    elif result == "loss":
        stats.losses = (stats.losses or 0) + 1
    elif result == "draw":
        stats.draws = (stats.draws or 0) + 1
    else:
        raise ValueError(f"Unknown result type: {result}")
    stats.elo = update_elo(old_elo, opponent_elo, result)
    stats.rank = calculate_rank(stats.elo)
    await session.commit()
    return stats.elo - old_elo

@connect
async def authenticate_user(login_or_email: str, password: str, session: AsyncSession) -> User | None:
    identifier = login_or_email.strip().lower()
    stmt = select(User).where((User.login == identifier) | (User.email == identifier))
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()
    if user and verify_password(password, user.password):
        return user
    return None

@connect
async def check_user_exists(session: AsyncSession, login: str | None = None, email: str | None = None) -> tuple[bool, bool]:
    login_exists = False
    email_exists = False
    if login is not None:
        login_norm = login.strip().lower()
        q = await session.execute(select(User).where(User.login == login_norm))
        login_exists = q.scalar_one_or_none() is not None
    if email is not None:
        email_norm = email.strip().lower()
        q = await session.execute(select(User).where(User.email == email_norm))
        email_exists = q.scalar_one_or_none() is not None
    return login_exists, email_exists

@connect
async def get_user_login(user_id: int, session: AsyncSession) -> str | None:
    user = await session.get(User, user_id)
    return user.login if user else None

@connect
async def get_user_id_by_login(login: str, session: AsyncSession) -> int | None:
    result = await session.execute(select(User).where(User.login == login))
    user = result.scalar_one_or_none()
    return user.id if user else None

@connect
async def get_user_email(user_id: int, session: AsyncSession) -> str | None:
    user = await session.get(User, user_id)
    return user.email if user else None

@connect
async def get_user_stats(user_id: int, session: AsyncSession) -> dict:
    stats = await session.get(UserStats, user_id)
    if not stats:
        return {"total_games": 0, "wins": 0, "draws": 0, "losses": 0, "elo": 0, "rank": calculate_rank(0)}
    return {
        "total_games": stats.total_games or 0,
        "wins": stats.wins or 0,
        "draws": stats.draws or 0,
        "losses": stats.losses or 0,
        "elo": stats.elo or 0,
        "rank": stats.rank,
    }

@connect
async def get_friends(user_id: int, session: AsyncSession) -> list[dict]:
    result = await session.execute(select(User).join(Friend, Friend.friend_id == User.id).where(Friend.user_id == user_id))
    users = result.scalars().all()
    return [{"id": u.id, "login": u.login} for u in users]

@connect
async def get_friend_requests(user_id: int, session: AsyncSession) -> dict:
    out_res = await session.execute(select(User).join(FriendRequest, FriendRequest.to_user_id == User.id).where(FriendRequest.from_user_id == user_id))
    inc_res = await session.execute(select(User).join(FriendRequest, FriendRequest.from_user_id == User.id).where(FriendRequest.to_user_id == user_id))
    outgoing = out_res.scalars().all()
    incoming = inc_res.scalars().all()
    return {
        "outgoing": [{"id": u.id, "login": u.login} for u in outgoing],
        "incoming": [{"id": u.id, "login": u.login} for u in incoming],
    }

@connect
async def search_users(query: str, user_id: int, session: AsyncSession) -> list[dict]:
    stmt = select(User).where(User.login.ilike(f"%{query.lower()}%"), User.id != user_id)
    result = await session.execute(stmt)
    users = result.scalars().all()
    friends = await get_friends(user_id)
    requests = await get_friend_requests(user_id)
    exclude_ids = {u["id"] for u in friends}
    outgoing_ids = {u["id"] for u in requests["outgoing"]}
    filtered = [u for u in users if u.id not in exclude_ids]
    return [{"id": u.id, "login": u.login, "requested": u.id in outgoing_ids} for u in filtered]

@connect
async def send_friend_request(from_id: int, to_id: int, session: AsyncSession) -> None:
    exists = await session.execute(select(FriendRequest).where(FriendRequest.from_user_id == from_id, FriendRequest.to_user_id == to_id))
    if exists.scalar_one_or_none():
        return
    opposite = await session.execute(select(FriendRequest).where(FriendRequest.from_user_id == to_id, FriendRequest.to_user_id == from_id))
    opp = opposite.scalar_one_or_none()
    if opp:
        await session.delete(opp)
        session.add(Friend(user_id=from_id, friend_id=to_id))
        session.add(Friend(user_id=to_id, friend_id=from_id))
        await session.commit()
        from src.app.achievements.friends import check_friend_achievements
        await check_friend_achievements(from_id)
        await check_friend_achievements(to_id)

        return
    fr = FriendRequest(from_user_id=from_id, to_user_id=to_id)
    session.add(fr)
    await session.commit()

@connect
async def cancel_friend_request(from_id: int, to_id: int, session: AsyncSession) -> None:
    req = await session.execute(select(FriendRequest).where(FriendRequest.from_user_id == from_id, FriendRequest.to_user_id == to_id))
    obj = req.scalar_one_or_none()
    if obj:
        await session.delete(obj)
        await session.commit()

@connect
async def remove_friend(user_id: int, friend_id: int, session: AsyncSession) -> None:
    await session.execute(
        text(
            """
            DELETE FROM friends
            WHERE (user_id = :u AND friend_id = :f) OR (user_id = :f AND friend_id = :u)
            """
        ),
        {"u": user_id, "f": friend_id},
    )
    await session.commit()

@connect
async def save_recorded_game(game_id: str, white_id: int | None, black_id: int | None, history: list[str], result: str, *, mode: str = "ranked", ranked: bool = True, session: AsyncSession) -> bool:
    stmt = (
        insert(RecordedGame)
        .values(
            id=game_id,
            white_id=white_id,
            black_id=black_id,
            history=json.dumps(history),
            result=result,
            timestamp=datetime.now(tz=MOSCOW_TZ),
            mode=mode,
            ranked=ranked,
        )
        .on_conflict_do_nothing(index_elements=["id"])
    )
    inserted = await session.execute(stmt)
    await session.commit()
    return inserted.rowcount == 1

@connect
async def get_recorded_game(game_id: str, session: AsyncSession) -> dict | None:
    game = await session.get(RecordedGame, game_id)
    if not game:
        return None
    white = await session.get(User, game.white_id)
    black = await session.get(User, game.black_id)
    def _name(user, uid):
        if user:
            return user.login
        if uid is None:
            return "Бот"
        return str(uid)
    return {
        "id": game.id,
        "history": json.loads(game.history),
        "result": game.result,
        "timestamp": game.timestamp.isoformat(),
        "mode": game.mode,
        "ranked": game.ranked,
        "players": {
            "white": _name(white, game.white_id),
            "black": _name(black, game.black_id),
        },
        "white_id": game.white_id,
        "black_id": game.black_id,
    }

@connect
async def record_game(user_id: int, mode: str, result: str, elo_change: int | None, session: AsyncSession, game_id: str | None = None) -> None:
    game = GameHistory(
        user_id=user_id,
        timestamp=datetime.now(tz=MOSCOW_TZ),
        mode=mode,
        result=result,
        elo_change=elo_change,
        game_id=game_id,
    )
    session.add(game)
    await session.commit()

@connect
async def get_user_history(user_id: int, session: AsyncSession, offset: int = 0, limit: int = 20) -> list[dict]:
    stmt = (
        select(GameHistory)
        .where(GameHistory.user_id == user_id)
        .order_by(GameHistory.timestamp.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await session.execute(stmt)
    games = result.scalars().all()
    return [
        {
            "id": g.game_id,
            "timestamp": g.timestamp.isoformat(),
            "mode": g.mode,
            "result": g.result,
            "elo_change": g.elo_change,
        }
        for g in games
    ]

@connect
async def count_bot_results(user_id: int, difficulty: str, result: str, session: AsyncSession) -> int:
    normalized = normalize_difficulty(difficulty)
    modes = {f"single_{normalized}", f"single_{difficulty}"}
    modes.update(
        f"single_{alias}"
        for alias, target in PROFILE_ALIASES.items()
        if target == normalized
    )
    stmt = select(func.count()).select_from(GameHistory).where(
        GameHistory.user_id == user_id,
        GameHistory.mode.in_(modes),
        GameHistory.result == result,
    )
    q = await session.execute(stmt)
    return q.scalar_one()

@connect
async def sum_elo_change_since(user_id: int, since: datetime, session: AsyncSession) -> int:
    stmt = (
        select(func.coalesce(func.sum(GameHistory.elo_change), 0))
        .where(
            GameHistory.user_id == user_id,
            GameHistory.timestamp >= since,
            GameHistory.elo_change != None,
        )
    )
    q = await session.execute(stmt)
    return q.scalar_one() or 0

@connect
async def set_2fa_secret(user_id: int, secret: str, session: AsyncSession) -> None:
    user = await session.get(User, user_id)
    user.twofa_secret = secret
    await session.commit()

@connect
async def enable_2fa(user_id: int, session: AsyncSession) -> None:
    user = await session.get(User, user_id)
    user.twofa_enabled = True
    await session.commit()

@connect
async def disable_2fa(user_id: int, session: AsyncSession) -> None:
    user = await session.get(User, user_id)
    user.twofa_enabled = False
    user.twofa_secret = None
    await session.commit()

@connect
async def get_2fa_info(user_id: int, session: AsyncSession) -> dict:
    user = await session.get(User, user_id)
    return {"enabled": bool(user.twofa_enabled), "secret": user.twofa_secret}

@connect
async def delete_user_account(user_id: int, session: AsyncSession) -> None:
    await session.execute(
        text("DELETE FROM friends WHERE user_id = :uid OR friend_id = :uid"),
        {"uid": user_id},
    )
    await session.execute(
        text(
            "DELETE FROM friend_requests WHERE from_user_id = :uid OR to_user_id = :uid"
        ),
        {"uid": user_id},
    )
    await session.execute(
        text("DELETE FROM game_history WHERE user_id = :uid"), {"uid": user_id}
    )
    await session.execute(
        text(
            "DELETE FROM recorded_games WHERE white_id = :uid OR black_id = :uid"
        ),
        {"uid": user_id},
    )
    await session.execute(
        text("DELETE FROM user_stats WHERE user_id = :uid"), {"uid": user_id}
    )
    await session.execute(
        text("DELETE FROM user_selected_checker_skins WHERE user_id = :uid"),
        {"uid": user_id},
    )
    await session.execute(
        text("DELETE FROM user_checker_skins WHERE user_id = :uid"),
        {"uid": user_id},
    )
    await session.execute(
        text("DELETE FROM user_wallets WHERE user_id = :uid"), {"uid": user_id}
    )
    user = await session.get(User, user_id)
    if user:
        await session.delete(user)
    await session.commit()


def _has_all_skin_access(user: User | None) -> bool:
    return bool(user and str(user.login).strip().lower() == STORE_ALL_ACCESS_LOGIN)


async def _ensure_wallet(session: AsyncSession, user_id: int) -> UserWallet:
    wallet = await session.get(UserWallet, user_id)
    if wallet is None:
        await session.execute(
            insert(UserWallet)
            .values(user_id=user_id, soft_balance=0, rub_balance=0)
            .on_conflict_do_nothing(index_elements=[UserWallet.user_id])
        )
        await session.flush()
        wallet = await session.get(UserWallet, user_id)
    if wallet is None:
        raise ValueError("WALLET_NOT_FOUND")
    return wallet


async def _owned_skin_ids(session: AsyncSession, user_id: int) -> set[str]:
    result = await session.execute(
        select(UserCheckerSkin.skin_id).where(UserCheckerSkin.user_id == user_id)
    )
    return {row[0] for row in result.all()}


async def _grant_skin(
    session: AsyncSession,
    user_id: int,
    skin_id: str,
    owned_ids: set[str],
    source: str,
) -> None:
    if skin_id in owned_ids:
        return
    await session.execute(
        insert(UserCheckerSkin)
        .values(
            user_id=user_id,
            skin_id=skin_id,
            acquired_at=datetime.now(tz=MOSCOW_TZ),
            source=source,
        )
        .on_conflict_do_nothing(index_elements=[UserCheckerSkin.user_id, UserCheckerSkin.skin_id])
    )
    owned_ids.add(skin_id)


async def _ensure_store_records(
    session: AsyncSession,
    user_id: int,
) -> tuple[User, UserWallet, set[str], UserSelectedCheckerSkin]:
    user = await session.get(User, user_id)
    if user is None:
        raise ValueError("USER_NOT_FOUND")

    wallet = await _ensure_wallet(session, user_id)
    owned_ids = await _owned_skin_ids(session, user_id)
    await _grant_skin(session, user_id, DEFAULT_CHECKER_SKIN_ID, owned_ids, "default")

    if _has_all_skin_access(user):
        for skin in CHECKER_SKINS:
            await _grant_skin(session, user_id, skin["id"], owned_ids, "owner_access")

    selected = await session.get(UserSelectedCheckerSkin, user_id)
    if selected is None:
        await session.execute(
            insert(UserSelectedCheckerSkin)
            .values(user_id=user_id, skin_id=DEFAULT_CHECKER_SKIN_ID)
            .on_conflict_do_nothing(index_elements=[UserSelectedCheckerSkin.user_id])
        )
        await session.flush()
        selected = await session.get(UserSelectedCheckerSkin, user_id)
    if selected is None:
        raise ValueError("SELECTED_SKIN_NOT_FOUND")

    if selected.skin_id not in CHECKER_SKIN_IDS or selected.skin_id not in owned_ids:
        selected.skin_id = DEFAULT_CHECKER_SKIN_ID

    await session.flush()
    return user, wallet, owned_ids, selected


def _wallet_payload(wallet: UserWallet) -> dict:
    return {
        "soft_balance": int(wallet.soft_balance or 0),
        "rub_balance": int(wallet.rub_balance or 0),
    }


def _skin_payload(skin: dict, owned_ids: set[str], selected_skin_id: str) -> dict:
    return {
        **skin,
        "owned": skin["id"] in owned_ids,
        "selected": skin["id"] == selected_skin_id,
    }


@connect
async def get_user_wallet(user_id: int, session: AsyncSession) -> dict:
    _user, wallet, _owned_ids, _selected = await _ensure_store_records(session, user_id)
    await session.commit()
    return _wallet_payload(wallet)


@connect
async def get_checker_store_state(user_id: int, session: AsyncSession) -> dict:
    user, wallet, owned_ids, selected = await _ensure_store_records(session, user_id)
    await session.commit()
    return {
        "wallet": _wallet_payload(wallet),
        "selected_skin": selected.skin_id,
        "all_access": _has_all_skin_access(user),
        "skins": [
            _skin_payload(skin, owned_ids, selected.skin_id)
            for skin in CHECKER_SKINS
        ],
    }


@connect
async def buy_checker_skin(user_id: int, skin_id: str, session: AsyncSession) -> dict:
    skin = checker_skin_by_id(skin_id)
    if skin is None:
        return {"status": "error", "error": "unknown_skin"}

    user, _wallet, owned_ids, selected = await _ensure_store_records(session, user_id)
    wallet = await session.get(UserWallet, user_id, with_for_update=True)
    if wallet is None:
        wallet = await _ensure_wallet(session, user_id)

    if skin_id in owned_ids:
        await session.commit()
        return {
            "status": "owned",
            "wallet": _wallet_payload(wallet),
            "selected_skin": selected.skin_id,
        }

    if _has_all_skin_access(user):
        await _grant_skin(session, user_id, skin_id, owned_ids, "owner_access")
        await session.commit()
        return {
            "status": "ok",
            "wallet": _wallet_payload(wallet),
            "selected_skin": selected.skin_id,
        }

    if skin["currency"] == "free":
        await _grant_skin(session, user_id, skin_id, owned_ids, "free")
    elif skin["currency"] == "soft":
        price = int(skin["soft_price"])
        if int(wallet.soft_balance or 0) < price:
            await session.commit()
            return {"status": "error", "error": "not_enough_soft", "wallet": _wallet_payload(wallet)}
        wallet.soft_balance = int(wallet.soft_balance or 0) - price
        await _grant_skin(session, user_id, skin_id, owned_ids, "soft")
    elif skin["currency"] == "rub":
        price = int(skin["rub_price"])
        if int(wallet.rub_balance or 0) < price:
            await session.commit()
            return {"status": "error", "error": "not_enough_rub", "wallet": _wallet_payload(wallet)}
        wallet.rub_balance = int(wallet.rub_balance or 0) - price
        await _grant_skin(session, user_id, skin_id, owned_ids, "rub")
    else:
        return {"status": "error", "error": "unknown_currency"}

    await session.commit()
    return {
        "status": "ok",
        "wallet": _wallet_payload(wallet),
        "selected_skin": selected.skin_id,
    }


@connect
async def select_checker_skin(user_id: int, skin_id: str, session: AsyncSession) -> dict:
    if skin_id not in CHECKER_SKIN_IDS:
        return {"status": "error", "error": "unknown_skin"}

    _user, wallet, owned_ids, selected = await _ensure_store_records(session, user_id)
    if skin_id not in owned_ids:
        await session.commit()
        return {
            "status": "error",
            "error": "skin_not_owned",
            "wallet": _wallet_payload(wallet),
            "selected_skin": selected.skin_id,
        }

    selected.skin_id = skin_id
    await session.commit()
    return {
        "status": "ok",
        "wallet": _wallet_payload(wallet),
        "selected_skin": selected.skin_id,
    }


@connect
async def get_selected_checker_skin(user_id: int, session: AsyncSession) -> str:
    _user, _wallet, _owned_ids, selected = await _ensure_store_records(session, user_id)
    await session.commit()
    return selected.skin_id


@connect
async def get_selected_checker_skins(user_ids_by_color: dict[str, int | None], session: AsyncSession) -> dict[str, str]:
    skins: dict[str, str] = {}
    for color, user_id in user_ids_by_color.items():
        if user_id is None:
            skins[color] = DEFAULT_CHECKER_SKIN_ID
            continue
        _user, _wallet, _owned_ids, selected = await _ensure_store_records(session, int(user_id))
        skins[color] = selected.skin_id
    await session.commit()
    return skins

@connect
async def ensure_achievements(achievements: list[dict], session: AsyncSession) -> None:
    for ach in achievements:
        q = await session.execute(
            select(Achievement).where(Achievement.code == ach["code"])
        )
        obj = q.scalar_one_or_none()
        if obj is None:
            obj = Achievement(
                code=ach["code"],
                title=ach["title"],
                description=ach["desc"],
                icon=ach["icon"],
            )
            session.add(obj)
        else:
            obj.title = ach["title"]
            obj.description = ach["desc"]
            obj.icon = ach["icon"]
    await session.commit()


@connect
async def unlock_achievement(user_id: int, code: str, session: AsyncSession) -> None:
    q = await session.execute(select(Achievement).where(Achievement.code == code))
    achievement = q.scalar_one_or_none()
    if not achievement:
        return
    exists = await session.execute(
        select(UserAchievement).where(
            UserAchievement.user_id == user_id,
            UserAchievement.achievement_id == achievement.id,
        )
    )
    if exists.scalar_one_or_none():
        return
    ua = UserAchievement(
        user_id=user_id,
        achievement_id=achievement.id,
        timestamp=datetime.now(tz=MOSCOW_TZ),
    )
    session.add(ua)
    await session.commit()


@connect
async def get_user_achievements(user_id: int, session: AsyncSession) -> list[str]:
    result = await session.execute(
        select(UserAchievement.achievement_id).where(UserAchievement.user_id == user_id)
    )
    ids = [row[0] for row in result.all()]
    if not ids:
        return []
    codes = await session.execute(
        select(Achievement.code).where(Achievement.id.in_(ids))
    )
    return [row[0] for row in codes.all()]


@connect
async def get_achievements(session: AsyncSession) -> list[dict]:
    canonical_codes = [ach["code"] for ach in ALL_ACHIEVEMENTS]
    result = await session.execute(
        select(Achievement).where(Achievement.code.in_(canonical_codes))
    )
    achievements = result.scalars().all()
    by_code = {achievement.code: achievement for achievement in achievements}
    return [
        {
            "code": code,
            "title": by_code[code].title,
            "desc": by_code[code].description,
            "icon": by_code[code].icon,
        }
        for code in canonical_codes
        if code in by_code
    ]

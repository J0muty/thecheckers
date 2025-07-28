from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Boolean
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.dialects.postgresql import CITEXT

Base = declarative_base()

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    login = Column(CITEXT, unique=True, nullable=False, index=True, comment="case-insensitive")
    email = Column(CITEXT, unique=True, nullable=False, index=True, comment="case-insensitive")
    password = Column(String(60), nullable=False, comment="bcrypt hash")
    twofa_enabled = Column(Boolean, nullable=False, default=False)
    twofa_secret = Column(String(64), nullable=True)
    stats = relationship("UserStats", back_populates="user", uselist=False)


class UserStats(Base):
    __tablename__ = "user_stats"

    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    total_games = Column(Integer, default=0)
    wins = Column(Integer, default=0)
    draws = Column(Integer, default=0)
    losses = Column(Integer, default=0)
    elo = Column(Integer, default=0)
    rank = Column("rang", String(50), default="Новичок")

    user = relationship("User", back_populates="stats")


class Friend(Base):
    __tablename__ = "friends"

    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    friend_id = Column(Integer, ForeignKey("users.id"), primary_key=True)


class FriendRequest(Base):
    __tablename__ = "friend_requests"

    id = Column(Integer, primary_key=True)
    from_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    to_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)


class GameHistory(Base):
    __tablename__ = "game_history"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    mode = Column(String(20), nullable=False)
    result = Column(String(10), nullable=False)
    elo_change = Column(Integer, nullable=True)
    game_id = Column(String(36), ForeignKey("recorded_games.id"), nullable=True)

class RecordedGame(Base):
    __tablename__ = "recorded_games"

    id = Column(String(36), primary_key=True)
    white_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    black_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    history = Column(String, nullable=False)
    result = Column(String(10), nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    mode = Column(String(20), nullable=False, default="ranked")
    ranked = Column(Boolean, nullable=False, default=True)

class Achievement(Base):
    __tablename__ = "achievements"

    id = Column(Integer, primary_key=True)
    code = Column(String(50), unique=True, nullable=False)
    title = Column(String(100), nullable=False)
    description = Column(String(255), nullable=False)
    icon = Column(String(50), nullable=False)


class UserAchievement(Base):
    __tablename__ = "user_achievements"

    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    achievement_id = Column(Integer, ForeignKey("achievements.id"), primary_key=True)
    timestamp = Column(DateTime(timezone=True), nullable=False)
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Index,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import relationship

from .database import Base, DB_SCHEMA


class Course(Base):
    __tablename__ = "courses"
    __table_args__ = {"schema": DB_SCHEMA}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    professor_id = Column(
        Integer,
        ForeignKey(f"{DB_SCHEMA}.users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    subject = Column(String, nullable=False)
    level = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    file_path = Column(String, nullable=True)
    # Stateless ingestion: store extracted (or retrieved) text directly, never the uploaded file.
    content_text = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    professor = relationship("User", back_populates="courses")
    questions = relationship("Question", back_populates="course", cascade="all, delete-orphan")
    progress = relationship("PlayerProgress", back_populates="course", cascade="all, delete-orphan")


class Question(Base):
    __tablename__ = "questions"
    __table_args__ = (
        Index("ix_questions_course_difficulty_id", "course_id", "difficulty_level", "id"),
        {"schema": DB_SCHEMA},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    course_id = Column(
        Integer,
        ForeignKey(f"{DB_SCHEMA}.courses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question = Column(Text, nullable=False)
    choices_json = Column(JSON, nullable=False)
    correct_answer = Column(String, nullable=False)
    difficulty_level = Column(String, nullable=False)

    course = relationship("Course", back_populates="questions")


class Player(Base):
    __tablename__ = "player"
    __table_args__ = {"schema": DB_SCHEMA}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String, nullable=False)
    age = Column(Integer, nullable=True)
    school_level = Column(String, nullable=True)
    experience_level = Column(String, nullable=True)
    game_level = Column(Integer, nullable=False, server_default="1")
    xp = Column(Integer, nullable=False, server_default="0")
    stars = Column(Integer, nullable=False, server_default="0")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    progress = relationship("PlayerProgress", back_populates="player", cascade="all, delete-orphan")


class PlayerProgress(Base):
    __tablename__ = "player_progress"
    __table_args__ = {"schema": DB_SCHEMA}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    player_id = Column(
        Integer,
        ForeignKey(f"{DB_SCHEMA}.player.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    course_id = Column(
        Integer,
        ForeignKey(f"{DB_SCHEMA}.courses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    score = Column(Float, nullable=False)
    difficulty_level = Column(String, nullable=False)
    emotion_score = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    player = relationship("Player", back_populates="progress")
    course = relationship("Course", back_populates="progress")


class GameSession(Base):
    __tablename__ = "sessions"
    __table_args__ = {"schema": DB_SCHEMA}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    player_id = Column(
        Integer,
        ForeignKey(f"{DB_SCHEMA}.player.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    course_id = Column(
        Integer,
        ForeignKey(f"{DB_SCHEMA}.courses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    final_score = Column(Float, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    used_question_ids = Column(JSON, nullable=False, server_default=text("'[]'::json"))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    answers = relationship("Answer", back_populates="session", cascade="all, delete-orphan")
    emotions = relationship("EmotionEvent", back_populates="session", cascade="all, delete-orphan")
    xapi_statements = relationship("XAPIStatement", back_populates="session", cascade="all, delete-orphan")


class Answer(Base):
    __tablename__ = "answers"
    __table_args__ = {"schema": DB_SCHEMA}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    session_id = Column(
        Integer,
        ForeignKey(f"{DB_SCHEMA}.sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question_id = Column(
        Integer,
        ForeignKey(f"{DB_SCHEMA}.questions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    selected_answer = Column(String, nullable=False)
    is_correct = Column(Boolean, nullable=False)
    time_spent_ms = Column(Integer, nullable=True)
    emotion = Column(String, nullable=True)
    emotion_confidence = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    session = relationship("GameSession", back_populates="answers")


class EmotionEvent(Base):
    __tablename__ = "emotions"
    __table_args__ = {"schema": DB_SCHEMA}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    session_id = Column(
        Integer,
        ForeignKey(f"{DB_SCHEMA}.sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question_id = Column(
        Integer,
        ForeignKey(f"{DB_SCHEMA}.questions.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    emotion = Column(String, nullable=False)
    confidence = Column(Float, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    session = relationship("GameSession", back_populates="emotions")


class XAPIStatement(Base):
    __tablename__ = "xapi_statements"
    __table_args__ = {"schema": DB_SCHEMA}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    session_id = Column(
        Integer,
        ForeignKey(f"{DB_SCHEMA}.sessions.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    statement_json = Column(JSON, nullable=False)
    sent = Column(Boolean, nullable=False, server_default="false")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    session = relationship("GameSession", back_populates="xapi_statements")


class User(Base):
    __tablename__ = "users"
    __table_args__ = {"schema": DB_SCHEMA}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    username = Column(String, nullable=False, unique=True, index=True)
    password_salt = Column(String, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False, index=True)  # professor|student
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    courses = relationship("Course", back_populates="professor")


class LevelProgress(Base):
    __tablename__ = "level_progress"
    __table_args__ = {"schema": DB_SCHEMA}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    player_id = Column(
        Integer,
        ForeignKey(f"{DB_SCHEMA}.player.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    course_id = Column(
        Integer,
        ForeignKey(f"{DB_SCHEMA}.courses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    session_id = Column(
        Integer,
        ForeignKey(f"{DB_SCHEMA}.sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    level_number = Column(Integer, nullable=False)
    accuracy = Column(Float, nullable=False)
    avg_time_ms = Column(Integer, nullable=True)
    emotion = Column(String, nullable=True)
    recommended_difficulty = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

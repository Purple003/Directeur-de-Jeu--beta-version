from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker

from datetime import datetime

import os

from .config import load_env_once

load_env_once()

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://adaptive_user:1234@localhost:5432/adaptive_game_db"
)

# Use a dedicated schema to avoid public-schema privilege issues.
DB_SCHEMA = os.getenv("DB_SCHEMA", "adaptive")

engine = create_engine(DATABASE_URL)
if engine.url.drivername.startswith("sqlite"):
    raise RuntimeError("SQLite is not supported for this project. Set DATABASE_URL to a PostgreSQL URL.")
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def ensure_schema() -> None:
    with engine.begin() as connection:
        connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {DB_SCHEMA}"))


def ensure_phase1_compatibility() -> None:
    """
    Lightweight migration to keep existing DBs working without Alembic.
    - Adds `file_path` to `courses` if missing.
    """
    inspector = inspect(engine)
    try:
        course_columns = {
            col["name"] for col in inspector.get_columns("courses", schema=DB_SCHEMA)
        }
    except Exception:
        return

    if "file_path" in course_columns:
        return

    with engine.begin() as connection:
        connection.execute(
            text(f"ALTER TABLE {DB_SCHEMA}.courses ADD COLUMN file_path VARCHAR")
        )


def ensure_phase3_compatibility() -> None:
    """
    Lightweight migration for session analytics fields.
    - Adds `final_score` and `duration_ms` to `sessions` if missing.
    """
    inspector = inspect(engine)
    try:
        session_columns = {
            col["name"] for col in inspector.get_columns("sessions", schema=DB_SCHEMA)
        }
    except Exception:
        return

    stmts: list[str] = []
    if "final_score" not in session_columns:
        stmts.append(f"ALTER TABLE {DB_SCHEMA}.sessions ADD COLUMN final_score DOUBLE PRECISION")
    if "duration_ms" not in session_columns:
        stmts.append(f"ALTER TABLE {DB_SCHEMA}.sessions ADD COLUMN duration_ms INTEGER")

    if not stmts:
        return

    with engine.begin() as connection:
        for stmt in stmts:
            connection.execute(text(stmt))


def ensure_phase4_compatibility() -> None:
    """
    Lightweight migration for player profile fields.
    - Adds age, school_level, experience_level to `player` if missing.
    """
    inspector = inspect(engine)
    try:
        cols = {col["name"] for col in inspector.get_columns("player", schema=DB_SCHEMA)}
    except Exception:
        return

    stmts: list[str] = []
    if "age" not in cols:
        stmts.append(f"ALTER TABLE {DB_SCHEMA}.player ADD COLUMN age INTEGER")
    if "school_level" not in cols:
        stmts.append(f"ALTER TABLE {DB_SCHEMA}.player ADD COLUMN school_level VARCHAR")
    if "experience_level" not in cols:
        stmts.append(f"ALTER TABLE {DB_SCHEMA}.player ADD COLUMN experience_level VARCHAR")
    if "game_level" not in cols:
        stmts.append(f"ALTER TABLE {DB_SCHEMA}.player ADD COLUMN game_level INTEGER NOT NULL DEFAULT 1")
    if "xp" not in cols:
        stmts.append(f"ALTER TABLE {DB_SCHEMA}.player ADD COLUMN xp INTEGER NOT NULL DEFAULT 0")
    if "stars" not in cols:
        stmts.append(f"ALTER TABLE {DB_SCHEMA}.player ADD COLUMN stars INTEGER NOT NULL DEFAULT 0")

    if not stmts:
        return

    with engine.begin() as connection:
        for stmt in stmts:
            connection.execute(text(stmt))


def ensure_phase5_compatibility() -> None:
    """
    Lightweight migration for:
    - course ownership (courses.professor_id)
    - answer-level emotions (answers.emotion, answers.emotion_confidence)
    """
    inspector = inspect(engine)

    try:
        course_cols = {col["name"] for col in inspector.get_columns("courses", schema=DB_SCHEMA)}
    except Exception:
        course_cols = set()

    try:
        answer_cols = {col["name"] for col in inspector.get_columns("answers", schema=DB_SCHEMA)}
    except Exception:
        answer_cols = set()

    stmts: list[str] = []
    if course_cols and "professor_id" not in course_cols:
        stmts.append(f"ALTER TABLE {DB_SCHEMA}.courses ADD COLUMN professor_id INTEGER")
        # FK constraint creation is skipped here for compatibility; Alembic should manage it in production.

    if answer_cols and "emotion" not in answer_cols:
        stmts.append(f"ALTER TABLE {DB_SCHEMA}.answers ADD COLUMN emotion VARCHAR")
    if answer_cols and "emotion_confidence" not in answer_cols:
        stmts.append(f"ALTER TABLE {DB_SCHEMA}.answers ADD COLUMN emotion_confidence DOUBLE PRECISION")

    if not stmts:
        return

    with engine.begin() as connection:
        for stmt in stmts:
            connection.execute(text(stmt))


def ensure_phase2_compatibility() -> None:
    """
    Lightweight migration for Phase 2 player system.

    If an older `player_progress` table exists with an incompatible schema (e.g. player_id as
    VARCHAR), we rename it to a legacy name so `create_all()` can create the new one.
    """
    inspector = inspect(engine)
    try:
        tables = set(inspector.get_table_names(schema=DB_SCHEMA))
    except Exception:
        return

    ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")

    def _rename_relation_if_exists(connection, relname: str, relkind: str) -> None:
        suffix = f"_legacy_{ts}"
        max_len = 63
        base = relname[: max_len - len(suffix)]
        new_name = base + suffix
        if relkind == "i":
            connection.execute(text(f"ALTER INDEX {DB_SCHEMA}.{relname} RENAME TO {new_name}"))
        elif relkind == "S":
            connection.execute(text(f"ALTER SEQUENCE {DB_SCHEMA}.{relname} RENAME TO {new_name}"))

    # If the table is missing but orphaned indexes/sequences exist (from a previous rename attempt),
    # rename them away so create_all() can succeed.
    if "player_progress" not in tables:
        with engine.begin() as connection:
            rows = connection.execute(
                text(
                    """
                    SELECT c.relname, c.relkind
                    FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE n.nspname = :schema
                      AND (
                        c.relname LIKE :ixpat
                        OR c.relname = 'player_progress_pkey'
                        OR c.relname = 'player_progress_id_seq'
                      )
                    """
                ),
                {"schema": DB_SCHEMA, "ixpat": f"ix_{DB_SCHEMA}_player_progress%"},
            ).fetchall()
            for relname, relkind in rows:
                _rename_relation_if_exists(connection, relname, relkind)
        return

    try:
        cols = inspector.get_columns("player_progress", schema=DB_SCHEMA)
    except Exception:
        return

    colmap = {c["name"]: c for c in cols}
    if "player_id" not in colmap:
        return

    player_id_type = str(colmap["player_id"].get("type", "")).lower()
    # We expect integer FK now. If it isn't, rename the table.
    if "int" in player_id_type:
        return

    legacy_name = f"player_progress_legacy_{ts}"

    with engine.begin() as connection:
        connection.execute(text(f"ALTER TABLE {DB_SCHEMA}.player_progress RENAME TO {legacy_name}"))
        # Rename common conflicting relations generated by SQLAlchemy for this table.
        rows = connection.execute(
            text(
                """
                SELECT c.relname, c.relkind
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = :schema
                  AND (
                    c.relname LIKE :ixpat
                    OR c.relname = 'player_progress_pkey'
                    OR c.relname = 'player_progress_id_seq'
                  )
                """
            ),
            {"schema": DB_SCHEMA, "ixpat": f"ix_{DB_SCHEMA}_player_progress%"},
        ).fetchall()
        for relname, relkind in rows:
            _rename_relation_if_exists(connection, relname, relkind)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

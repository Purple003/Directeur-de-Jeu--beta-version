"""Add session used question tracking

Revision ID: 20260429_01
Revises: 20260310_01
Create Date: 2026-04-29
"""

from __future__ import annotations

from alembic import op


revision = "20260429_01"
down_revision = "20260310_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS adaptive")
    op.execute(
        "ALTER TABLE adaptive.sessions "
        "ADD COLUMN IF NOT EXISTS used_question_ids JSON NOT NULL DEFAULT '[]'::json"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_questions_course_difficulty_id "
        "ON adaptive.questions (course_id, difficulty_level, id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS adaptive.ix_questions_course_difficulty_id")
    op.execute("ALTER TABLE adaptive.sessions DROP COLUMN IF EXISTS used_question_ids")

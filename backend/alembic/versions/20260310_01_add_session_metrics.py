"""Add Session Analytics Fields (final_score, duration_ms)

Revision ID: 20260310_01
Revises: 
Create Date: 2026-03-10
"""

from __future__ import annotations

from alembic import op


revision = "20260310_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Keep upgrades idempotent for existing DBs.
    op.execute("CREATE SCHEMA IF NOT EXISTS adaptive")
    op.execute("ALTER TABLE adaptive.sessions ADD COLUMN IF NOT EXISTS final_score DOUBLE PRECISION")
    op.execute("ALTER TABLE adaptive.sessions ADD COLUMN IF NOT EXISTS duration_ms INTEGER")


def downgrade() -> None:
    # Downgrade is best-effort; may fail if column is referenced elsewhere.
    op.execute("ALTER TABLE adaptive.sessions DROP COLUMN IF EXISTS duration_ms")
    op.execute("ALTER TABLE adaptive.sessions DROP COLUMN IF EXISTS final_score")


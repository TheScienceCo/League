"""Initial schema: replays and their players.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-09-09
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "replays",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("replay_id", sa.String(length=64), nullable=False),
        sa.Column("filename", sa.String(length=500), nullable=False),
        sa.Column("map_name", sa.String(length=255), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("game_version", sa.String(length=50), nullable=True),
        sa.Column("analysis", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_replays"),
        sa.UniqueConstraint("replay_id", name="uq_replays_replay_id"),
    )
    op.create_index("ix_replays_created_at", "replays", ["created_at"])

    op.create_table(
        "replay_players",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("replay_pk", sa.Integer(), nullable=False),
        sa.Column("player_number", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("civilization", sa.String(length=100), nullable=False),
        sa.Column("winner", sa.Boolean(), nullable=True),
        sa.Column("feudal_ms", sa.Integer(), nullable=True),
        sa.Column("castle_ms", sa.Integer(), nullable=True),
        sa.Column("imperial_ms", sa.Integer(), nullable=True),
        sa.Column("eapm", sa.Integer(), nullable=True),
        sa.Column("opening", sa.String(length=50), nullable=True),
        sa.ForeignKeyConstraint(
            ["replay_pk"], ["replays.id"],
            name="fk_replay_players_replay_pk_replays", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_replay_players"),
    )
    op.create_index("ix_replay_players_name", "replay_players", ["name"])
    op.create_index("ix_replay_players_civilization", "replay_players", ["civilization"])


def downgrade() -> None:
    op.drop_index("ix_replay_players_civilization", table_name="replay_players")
    op.drop_index("ix_replay_players_name", table_name="replay_players")
    op.drop_table("replay_players")
    op.drop_index("ix_replays_created_at", table_name="replays")
    op.drop_table("replays")

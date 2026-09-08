"""Create initial AoE2 analytics schema.

Revision ID: 0002_aoe2_initial
Revises: 0001_initial_schema
Create Date: 2024-09-08 12:00:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0002_aoe2_initial"
down_revision: Union[str, None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create AoE2 analytics tables."""

    # Players table
    op.create_table(
        "players",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=255), nullable=False),
        sa.Column("steam_id", sa.Integer(), nullable=True),
        sa.Column("total_games", sa.Integer(), server_default="0", nullable=False),
        sa.Column("wins", sa.Integer(), server_default="0", nullable=False),
        sa.Column("losses", sa.Integer(), server_default="0", nullable=False),
        sa.Column("mean_elo", sa.Float(), server_default="1000.0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_players"),
        sa.UniqueConstraint("username", name="uq_players_username"),
        sa.UniqueConstraint("steam_id", name="uq_players_steam_id"),
    )
    op.create_index("ix_players_username", "players", ["username"])

    # Matches table
    op.create_table(
        "matches",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("replay_file_id", sa.Integer(), nullable=True),
        sa.Column("map_type", sa.Enum("arabia", "nomad", "black_forest", "coastal", "continental", "custom", name="maptype"), server_default="arabia", nullable=False),
        sa.Column("map_name", sa.String(length=255), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=False),
        sa.Column("player_count", sa.Integer(), nullable=False),
        sa.Column("winner_id", sa.Integer(), nullable=True),
        sa.Column("patch_version", sa.String(length=50), server_default="latest", nullable=False),
        sa.Column("game_version", sa.String(length=50), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["winner_id"], ["players.id"], name="fk_matches_winner_id_players"),
        sa.PrimaryKeyConstraint("id", name="pk_matches"),
    )
    op.create_index("ix_matches_duration", "matches", ["duration_seconds"])
    op.create_index("ix_matches_created_at", "matches", ["created_at"])

    # Replay files table
    op.create_table(
        "replay_files",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("match_id", sa.Integer(), nullable=True),
        sa.Column("uploader_id", sa.Integer(), nullable=True),
        sa.Column("original_filename", sa.String(length=500), nullable=False),
        sa.Column("file_hash", sa.String(length=64), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("storage_path", sa.String(length=500), nullable=False),
        sa.Column("status", sa.Enum("uploaded", "parsing", "parsed", "analyzing", "completed", "failed", name="replayprocessingstatus"), server_default="uploaded", nullable=False),
        sa.Column("parsing_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("parsing_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("parse_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], name="fk_replay_files_match_id_matches"),
        sa.ForeignKeyConstraint(["uploader_id"], ["players.id"], name="fk_replay_files_uploader_id_players"),
        sa.PrimaryKeyConstraint("id", name="pk_replay_files"),
        sa.UniqueConstraint("file_hash", name="uq_replay_files_file_hash"),
    )

    # Match players table (junction)
    op.create_table(
        "match_players",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("match_id", sa.Integer(), nullable=False),
        sa.Column("player_id", sa.Integer(), nullable=False),
        sa.Column("civilization", sa.Enum("britons", "franks", "goths", "teutons", "japanese", "mongols", "vikings", "aztecs", "mayans", "chinese", "indians", "persians", "ethiopians", "koreans", "italians", "portuguese", "berbers", "bulgarians", "georgians", "turks", "vietnamese", "malians", "poles", name="civilization"), nullable=False),
        sa.Column("team", sa.Integer(), nullable=True),
        sa.Column("result", sa.Enum("win", "loss", "draw", name="gameresult"), nullable=False),
        sa.Column("starting_position", sa.Integer(), nullable=True),
        sa.Column("elo_before", sa.Float(), nullable=True),
        sa.Column("elo_after", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], name="fk_match_players_match_id_matches"),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"], name="fk_match_players_player_id_players"),
        sa.PrimaryKeyConstraint("id", name="pk_match_players"),
        sa.UniqueConstraint("match_id", "player_id", name="uq_match_player"),
    )
    op.create_index("ix_match_players_player_id", "match_players", ["player_id"])

    # Events table
    op.create_table(
        "events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("match_id", sa.Integer(), nullable=False),
        sa.Column("player_id", sa.Integer(), nullable=True),
        sa.Column("timestamp_ms", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.Enum("age_up", "build_completed", "build_destroyed", "unit_created", "unit_died", "technology_researched", "resource_tribute", "villager_assigned", "research_started", "unit_attacked", "formation_changed", name="eventtype"), nullable=False),
        sa.Column("data", postgresql.JSON(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], name="fk_events_match_id_matches"),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"], name="fk_events_player_id_players"),
        sa.PrimaryKeyConstraint("id", name="pk_events"),
    )
    op.create_index("ix_events_match_id", "events", ["match_id"])
    op.create_index("ix_events_timestamp", "events", ["timestamp_ms"])
    op.create_index("ix_events_player_id", "events", ["player_id"])
    op.create_index("ix_events_type", "events", ["event_type"])

    # Game states table
    op.create_table(
        "game_states",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("match_id", sa.Integer(), nullable=False),
        sa.Column("player_id", sa.Integer(), nullable=False),
        sa.Column("timestamp_ms", sa.Integer(), nullable=False),
        sa.Column("snapshot", postgresql.JSON(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], name="fk_game_states_match_id_matches"),
        sa.PrimaryKeyConstraint("id", name="pk_game_states"),
    )
    op.create_index("ix_game_states_match_id", "game_states", ["match_id"])
    op.create_index("ix_game_states_timestamp", "game_states", ["timestamp_ms"])

    # Engagements table
    op.create_table(
        "engagements",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("match_id", sa.Integer(), nullable=False),
        sa.Column("start_timestamp_ms", sa.Integer(), nullable=False),
        sa.Column("end_timestamp_ms", sa.Integer(), nullable=False),
        sa.Column("participants", postgresql.JSON(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("army_value_destroyed_p1", sa.Float(), nullable=True),
        sa.Column("army_value_destroyed_p2", sa.Float(), nullable=True),
        sa.Column("units_killed_p1", sa.Integer(), nullable=True),
        sa.Column("units_killed_p2", sa.Integer(), nullable=True),
        sa.Column("location", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("strategic_value", sa.String(length=50), nullable=True),
        sa.Column("outcome", sa.String(length=50), nullable=True),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], name="fk_engagements_match_id_matches"),
        sa.PrimaryKeyConstraint("id", name="pk_engagements"),
    )
    op.create_index("ix_engagements_timestamp", "engagements", ["start_timestamp_ms"])

    # Match metrics table
    op.create_table(
        "match_metrics",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("match_id", sa.Integer(), nullable=False),
        sa.Column("player_id", sa.Integer(), nullable=False),
        sa.Column("feature_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("metrics_version", sa.String(length=50), server_default="1.0", nullable=False),
        sa.Column("tc_idle_time_ms", sa.Integer(), nullable=True),
        sa.Column("villager_idle_time_estimated_ms", sa.Integer(), nullable=True),
        sa.Column("resource_float_peak", sa.Float(), nullable=True),
        sa.Column("resource_float_average", sa.Float(), nullable=True),
        sa.Column("resources_collected_total", sa.Float(), nullable=True),
        sa.Column("age_up_timing_ms", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("first_military_building_time_ms", sa.Integer(), nullable=True),
        sa.Column("first_military_unit_time_ms", sa.Integer(), nullable=True),
        sa.Column("military_value_killed", sa.Float(), nullable=True),
        sa.Column("military_value_lost", sa.Float(), nullable=True),
        sa.Column("military_production_uptime", sa.Float(), nullable=True),
        sa.Column("engagement_efficiency", sa.Float(), nullable=True),
        sa.Column("scouting_coverage_percent", sa.Float(), nullable=True),
        sa.Column("time_to_enemy_discovery_ms", sa.Integer(), nullable=True),
        sa.Column("reaction_latency_ms", sa.Integer(), nullable=True),
        sa.Column("tempo_score", sa.Float(), nullable=True),
        sa.Column("all_metrics", postgresql.JSON(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], name="fk_match_metrics_match_id_matches"),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"], name="fk_match_metrics_player_id_players"),
        sa.PrimaryKeyConstraint("id", name="pk_match_metrics"),
        sa.UniqueConstraint("match_id", name="uq_match_metrics_match_id"),
    )

    # Player metric percentiles table
    op.create_table(
        "player_metric_percentiles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("player_id", sa.Integer(), nullable=False),
        sa.Column("metric_name", sa.String(length=255), nullable=False),
        sa.Column("elo_band_min", sa.Integer(), nullable=False),
        sa.Column("elo_band_max", sa.Integer(), nullable=False),
        sa.Column("percentile_rank", sa.Float(), nullable=False),
        sa.Column("value", sa.Float(), nullable=True),
        sa.Column("cohort_size", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"], name="fk_player_metric_percentiles_player_id_players"),
        sa.PrimaryKeyConstraint("id", name="pk_player_metric_percentiles"),
        sa.UniqueConstraint("player_id", "metric_name", "elo_band_min", name="uq_player_metric_elo"),
    )
    op.create_index("ix_player_metric_percentiles_player_id", "player_metric_percentiles", ["player_id"])

    # Model versions table
    op.create_table(
        "model_versions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("model_name", sa.String(length=255), nullable=False),
        sa.Column("version", sa.String(length=50), nullable=False),
        sa.Column("model_path", sa.String(length=500), nullable=False),
        sa.Column("training_samples", sa.Integer(), nullable=True),
        sa.Column("metrics_json", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_model_versions"),
        sa.UniqueConstraint("model_name", "version", name="uq_model_name_version"),
    )

    # Coaching insights table
    op.create_table(
        "coaching_insights",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("match_id", sa.Integer(), nullable=False),
        sa.Column("player_id", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("magnitude", sa.Float(), nullable=True),
        sa.Column("evidence_text", sa.Text(), nullable=True),
        sa.Column("recommendation", sa.Text(), nullable=True),
        sa.Column("estimated_impact", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], name="fk_coaching_insights_match_id_matches"),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"], name="fk_coaching_insights_player_id_players"),
        sa.PrimaryKeyConstraint("id", name="pk_coaching_insights"),
    )
    op.create_index("ix_coaching_insights_match_id", "coaching_insights", ["match_id"])


def downgrade() -> None:
    """Drop AoE2 analytics tables."""

    op.drop_index("ix_coaching_insights_match_id", table_name="coaching_insights")
    op.drop_table("coaching_insights")

    op.drop_table("model_versions")

    op.drop_index("ix_player_metric_percentiles_player_id", table_name="player_metric_percentiles")
    op.drop_table("player_metric_percentiles")

    op.drop_table("match_metrics")

    op.drop_index("ix_engagements_timestamp", table_name="engagements")
    op.drop_table("engagements")

    op.drop_index("ix_game_states_timestamp", table_name="game_states")
    op.drop_index("ix_game_states_match_id", table_name="game_states")
    op.drop_table("game_states")

    op.drop_index("ix_events_type", table_name="events")
    op.drop_index("ix_events_player_id", table_name="events")
    op.drop_index("ix_events_timestamp", table_name="events")
    op.drop_index("ix_events_match_id", table_name="events")
    op.drop_table("events")

    op.drop_index("ix_match_players_player_id", table_name="match_players")
    op.drop_table("match_players")

    op.drop_table("replay_files")

    op.drop_index("ix_matches_created_at", table_name="matches")
    op.drop_index("ix_matches_duration", table_name="matches")
    op.drop_table("matches")

    op.drop_index("ix_players_username", table_name="players")
    op.drop_table("players")

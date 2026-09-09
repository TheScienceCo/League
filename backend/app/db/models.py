"""ORM models.

The schema divides into four layers:

* **Identity** - `Summoner`, `LeagueEntry`.
* **Normalized Match-V5 storage** - `Match`, `MatchTeam`, `MatchParticipant`,
  `TimelineFrame`, `TimelineEvent`. These are faithful copies of Riot payloads;
  nothing derived lives here.
* **Derived analytics** - `ParticipantFeatures`, `RoamEvent`, `ObjectiveSetup`,
  `CohortStat`, `MapRiskCell`. Everything in this layer is recomputable from the
  layer above, which is the point of keeping the boundary sharp.
* **Operational** - `IngestJob`, `MLModelRecord`.

Rows are related by `match_id` / `puuid` and joined explicitly in queries rather
than through ORM relationships: the analytics paths do bulk selects over many
matches at once, where lazy-loading a relationship per row would be a trap.

Column types come from `app.db.types` so the suite can run on SQLite while
Postgres gets JSONB, native arrays and 64-bit keys.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.db.types import BigIntPK, IntArray, JSONVariant


class JobStatus(StrEnum):
    """Lifecycle of an ingestion job.

    `PARTIAL` is its own state rather than a flavour of failure: a run that
    ingested most of a player's matches and lost a few to Riot returning 5xx is
    useful, and the caller should be able to tell it apart from both a clean run
    and a total one.
    """

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------


class Summoner(Base, TimestampMixin):
    __tablename__ = "summoners"

    puuid: Mapped[str] = mapped_column(String(78), primary_key=True)
    game_name: Mapped[str | None] = mapped_column(String(64))
    tag_line: Mapped[str | None] = mapped_column(String(16))
    platform: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
    summoner_id: Mapped[str | None] = mapped_column(String(64))
    account_id: Mapped[str | None] = mapped_column(String(64))
    profile_icon_id: Mapped[int | None] = mapped_column(Integer)
    summoner_level: Mapped[int | None] = mapped_column(Integer)
    revision_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_ingested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_summoners_riot_id", "game_name", "tag_line", "platform"),
    )


class LeagueEntry(Base, TimestampMixin):
    __tablename__ = "league_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    puuid: Mapped[str] = mapped_column(
        String(78), ForeignKey("summoners.puuid", ondelete="CASCADE"), nullable=False
    )
    queue_type: Mapped[str] = mapped_column(String(32), nullable=False)
    tier: Mapped[str | None] = mapped_column(String(16))
    division: Mapped[str | None] = mapped_column(String(4))
    league_points: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    wins: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    losses: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    hot_streak: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    veteran: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    inactive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    fresh_blood: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: Tier and division collapsed onto one continuous axis, so rank can be a
    #: model feature and a cohort boundary without special-casing.
    rank_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    snapshot_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("puuid", "queue_type", name="uq_league_entry_puuid_queue"),
    )


# ---------------------------------------------------------------------------
# Normalized Match-V5 storage
# ---------------------------------------------------------------------------


class Match(Base, TimestampMixin):
    __tablename__ = "matches"

    match_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    platform: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
    region: Mapped[str] = mapped_column(String(16), nullable=False)
    queue_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    game_mode: Mapped[str | None] = mapped_column(String(32))
    game_type: Mapped[str | None] = mapped_column(String(32))
    map_id: Mapped[int | None] = mapped_column(Integer)
    game_version: Mapped[str | None] = mapped_column(String(32))
    #: Major.minor only. Cohorts are keyed on this, so the build number would
    #: fragment them for no analytical gain.
    patch: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    game_creation: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    game_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    game_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    game_duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    winning_team_id: Mapped[int | None] = mapped_column(Integer)
    #: Ingestion is staged: a match row can exist before its timeline is fetched
    #: and before features are computed. These flags drive the backfill.
    timeline_ingested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    features_computed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    data_source: Mapped[str] = mapped_column(String(16), nullable=False, default="riot")

    __table_args__ = (Index("ix_matches_patch_queue", "patch", "queue_id"),)


class MatchTeam(Base):
    __tablename__ = "match_teams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("matches.match_id", ondelete="CASCADE"), nullable=False
    )
    team_id: Mapped[int] = mapped_column(Integer, nullable=False)
    win: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    champion_kills: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    dragon_kills: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    baron_kills: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    herald_kills: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tower_kills: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    inhibitor_kills: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    first_blood: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    first_tower: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    first_dragon: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    first_baron: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    bans: Mapped[list[Any]] = mapped_column(JSONVariant, nullable=False, default=list)

    __table_args__ = (UniqueConstraint("match_id", "team_id", name="uq_match_team"),)


class MatchParticipant(Base):
    __tablename__ = "match_participants"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    match_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("matches.match_id", ondelete="CASCADE"), nullable=False
    )
    puuid: Mapped[str] = mapped_column(String(78), nullable=False, index=True)
    participant_id: Mapped[int] = mapped_column(Integer, nullable=False)
    team_id: Mapped[int] = mapped_column(Integer, nullable=False)
    win: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    riot_id_game_name: Mapped[str | None] = mapped_column(String(64))
    riot_id_tagline: Mapped[str | None] = mapped_column(String(16))
    champion_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    champion_name: Mapped[str | None] = mapped_column(String(32))
    champ_level: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: The role used for cohorts and for pairing a player against their lane
    #: opponent. `individual_position` and `lane` are kept for provenance.
    team_position: Mapped[str] = mapped_column(String(16), nullable=False)
    individual_position: Mapped[str | None] = mapped_column(String(16))
    lane: Mapped[str | None] = mapped_column(String(16))

    kills: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deaths: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    assists: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    gold_earned: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    gold_spent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_minions_killed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    neutral_minions_killed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    total_damage_to_champions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    physical_damage_to_champions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    magic_damage_to_champions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    true_damage_to_champions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_damage_taken: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    damage_self_mitigated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_heals_on_teammates: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    damage_dealt_to_objectives: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    damage_dealt_to_turrets: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    vision_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    wards_placed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    wards_killed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    detector_wards_placed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    vision_wards_bought: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    turret_takedowns: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    dragon_takedowns: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    baron_takedowns: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    objectives_stolen: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    time_ccing_others: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_time_spent_dead: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    longest_time_spent_living: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    first_blood_kill: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    first_tower_kill: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    summoner_spell_1: Mapped[int | None] = mapped_column(Integer)
    summoner_spell_2: Mapped[int | None] = mapped_column(Integer)
    items: Mapped[list[Any]] = mapped_column(JSONVariant, nullable=False, default=list)
    perks: Mapped[dict[str, Any]] = mapped_column(JSONVariant, nullable=False, default=dict)

    #: Rank at the time of the match, denormalized off `league_entries` so that
    #: cohort queries do not have to join identity for every row.
    rank_tier: Mapped[str | None] = mapped_column(String(16), index=True)
    rank_division: Mapped[str | None] = mapped_column(String(4))
    rank_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    tier_group: Mapped[str] = mapped_column(String(16), nullable=False, index=True)

    __table_args__ = (
        UniqueConstraint("match_id", "participant_id", name="uq_match_participant"),
        Index("ix_participants_cohort", "team_position", "champion_id", "tier_group"),
        Index("ix_participants_puuid_match", "puuid", "match_id"),
    )

    @property
    def cs(self) -> int:
        """Creep score: lane minions plus jungle camps.

        Riot reports the two separately, but every rate and differential built
        on CS wants them summed - a jungler's farm is mostly neutral camps and a
        laner's mostly minions, so counting either alone misreads one role.
        """
        return self.total_minions_killed + self.neutral_minions_killed


class TimelineFrame(Base):
    """One row per (participant, minute)."""

    __tablename__ = "timeline_frames"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    match_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("matches.match_id", ondelete="CASCADE"), nullable=False
    )
    participant_id: Mapped[int] = mapped_column(Integer, nullable=False)
    timestamp_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    minute: Mapped[int] = mapped_column(Integer, nullable=False)

    total_gold: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_gold: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    xp: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    level: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    minions_killed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    jungle_minions_killed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    time_enemy_spent_controlled: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    position_x: Mapped[float | None] = mapped_column(Float)
    position_y: Mapped[float | None] = mapped_column(Float)
    damage_done_to_champions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    damage_taken: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint("match_id", "participant_id", "timestamp_ms", name="uq_frame"),
        Index("ix_frames_lookup", "match_id", "participant_id", "timestamp_ms"),
        Index("ix_frames_match_minute", "match_id", "minute"),
    )


class TimelineEvent(Base):
    """Kills, wards, objectives and buildings.

    The union of every event shape Riot emits is wide and sparse, so the
    consumed fields are columns and the original payload is kept in `raw` -
    which means a new analysis can reach a field nobody broke out yet without a
    re-ingest.
    """

    __tablename__ = "timeline_events"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    match_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("matches.match_id", ondelete="CASCADE"), nullable=False
    )
    timestamp_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    minute: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)

    participant_id: Mapped[int | None] = mapped_column(Integer)
    killer_id: Mapped[int | None] = mapped_column(Integer)
    victim_id: Mapped[int | None] = mapped_column(Integer)
    assisting_participant_ids: Mapped[list[int]] = mapped_column(
        IntArray, nullable=False, default=list
    )
    team_id: Mapped[int | None] = mapped_column(Integer)
    position_x: Mapped[float | None] = mapped_column(Float)
    position_y: Mapped[float | None] = mapped_column(Float)

    monster_type: Mapped[str | None] = mapped_column(String(32))
    monster_sub_type: Mapped[str | None] = mapped_column(String(32))
    building_type: Mapped[str | None] = mapped_column(String(32))
    tower_type: Mapped[str | None] = mapped_column(String(32))
    lane_type: Mapped[str | None] = mapped_column(String(32))
    ward_type: Mapped[str | None] = mapped_column(String(32))
    creator_id: Mapped[int | None] = mapped_column(Integer)
    item_id: Mapped[int | None] = mapped_column(Integer)
    kill_type: Mapped[str | None] = mapped_column(String(32))
    bounty: Mapped[int | None] = mapped_column(Integer)
    shutdown_bounty: Mapped[int | None] = mapped_column(Integer)
    raw: Mapped[dict[str, Any]] = mapped_column(JSONVariant, nullable=False, default=dict)

    __table_args__ = (
        Index("ix_events_match_ts", "match_id", "timestamp_ms"),
        Index("ix_events_match_type", "match_id", "type"),
        Index("ix_events_victim", "match_id", "victim_id"),
    )


# ---------------------------------------------------------------------------
# Derived analytics
# ---------------------------------------------------------------------------


class ParticipantFeatures(Base, TimestampMixin):
    """The boundary: everything here is derived and recomputable.

    A null means "not computable for this game", never zero - a match that ended
    at minute nine genuinely has no `gold_diff_10`, and imputing one would put a
    fabricated value into every cohort that game belongs to.
    """

    __tablename__ = "participant_features"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    match_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("matches.match_id", ondelete="CASCADE"), nullable=False
    )
    puuid: Mapped[str] = mapped_column(String(78), nullable=False, index=True)
    participant_id: Mapped[int] = mapped_column(Integer, nullable=False)

    # Cohort keys.
    team_position: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    champion_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    tier_group: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    rank_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    patch: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    queue_id: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_bucket: Mapped[str] = mapped_column(String(8), nullable=False)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    win: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Laning, measured against the lane opponent. Null when no opponent pairs.
    gold_diff_10: Mapped[float | None] = mapped_column(Float)
    gold_diff_15: Mapped[float | None] = mapped_column(Float)
    xp_diff_10: Mapped[float | None] = mapped_column(Float)
    xp_diff_15: Mapped[float | None] = mapped_column(Float)
    cs_diff_10: Mapped[float | None] = mapped_column(Float)
    cs_diff_15: Mapped[float | None] = mapped_column(Float)

    # Rates.
    cs_per_min: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    cs_per_min_first_15: Mapped[float | None] = mapped_column(Float)
    gold_per_min: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    damage_per_min: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    kda: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    kill_participation: Mapped[float | None] = mapped_column(Float)
    early_deaths: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deaths_per_10min: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    solo_kills: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    solo_deaths: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    solo_kill_diff: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Shares and efficiency.
    damage_per_gold: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    damage_share: Mapped[float | None] = mapped_column(Float)
    gold_share: Mapped[float | None] = mapped_column(Float)
    damage_taken_share: Mapped[float | None] = mapped_column(Float)
    #: Resource Conversion Efficiency: output share over resource share, then
    #: residualized against the cohort - hence both a raw and a z form.
    rce_raw: Mapped[float | None] = mapped_column(Float)
    rce_z: Mapped[float | None] = mapped_column(Float)

    # Vision.
    vision_score_per_min: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    wards_placed_per_min: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    wards_cleared_per_min: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    control_wards_per_min: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # Objectives.
    objective_participation: Mapped[float | None] = mapped_column(Float)
    dragon_participation: Mapped[float | None] = mapped_column(Float)
    baron_herald_participation: Mapped[float | None] = mapped_column(Float)
    objective_setup_score: Mapped[float | None] = mapped_column(Float)
    deaths_before_objectives: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Converting a lead - and playing from behind.
    team_gold_diff_15: Mapped[float | None] = mapped_column(Float)
    had_lead_at_15: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    converted_lead: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    time_ahead_share: Mapped[float | None] = mapped_column(Float)
    dpm_while_ahead: Mapped[float | None] = mapped_column(Float)
    dpm_while_behind: Mapped[float | None] = mapped_column(Float)
    cspm_while_ahead: Mapped[float | None] = mapped_column(Float)
    cspm_while_behind: Mapped[float | None] = mapped_column(Float)
    gold_diff_slope_10_20: Mapped[float | None] = mapped_column(Float)

    # Roaming.
    roam_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    roam_value_total: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    roam_value_per_roam: Mapped[float | None] = mapped_column(Float)
    roam_cs_sacrificed: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    roam_success_rate: Mapped[float | None] = mapped_column(Float)

    # Positional risk, against the empirical map risk surface.
    mean_position_risk: Mapped[float | None] = mapped_column(Float)
    expected_deaths: Mapped[float | None] = mapped_column(Float)
    deaths_above_expected: Mapped[float | None] = mapped_column(Float)
    high_risk_exposure_share: Mapped[float | None] = mapped_column(Float)

    #: Room for a feature to be trialled before it earns a column.
    extra: Mapped[dict[str, Any]] = mapped_column(JSONVariant, nullable=False, default=dict)

    __table_args__ = (
        UniqueConstraint("match_id", "puuid", name="uq_features_match_puuid"),
        Index("ix_features_cohort", "team_position", "champion_id", "tier_group", "patch"),
        Index("ix_features_puuid_patch", "puuid", "patch"),
    )


class RoamEvent(Base):
    """A detected excursion out of lane, with what it cost and what it bought."""

    __tablename__ = "roam_events"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    match_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("matches.match_id", ondelete="CASCADE"), nullable=False
    )
    puuid: Mapped[str] = mapped_column(String(78), nullable=False, index=True)
    participant_id: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)

    start_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    end_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    target_zone: Mapped[str] = mapped_column(String(24), nullable=False)

    kills: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    assists: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deaths: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    objectives: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    gold_gained: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    xp_gained: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    #: What staying in lane would have earned - the roam's opportunity cost.
    cs_sacrificed: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    xp_sacrificed: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    value: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    expected_value: Mapped[float | None] = mapped_column(Float)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (Index("ix_roams_match_puuid", "match_id", "puuid"),)


class ObjectiveSetup(Base):
    """How a player was positioned in the window before an objective spawned."""

    __tablename__ = "objective_setups"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    match_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("matches.match_id", ondelete="CASCADE"), nullable=False
    )
    puuid: Mapped[str] = mapped_column(String(78), nullable=False, index=True)
    participant_id: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)

    objective_type: Mapped[str] = mapped_column(String(32), nullable=False)
    objective_sub_type: Mapped[str | None] = mapped_column(String(32))
    objective_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    team_secured: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    player_credited: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    #: Distance from the objective at 30/60/90 seconds before it spawned.
    distance_30s: Mapped[float | None] = mapped_column(Float)
    distance_60s: Mapped[float | None] = mapped_column(Float)
    distance_90s: Mapped[float | None] = mapped_column(Float)
    arrival_lead_seconds: Mapped[float | None] = mapped_column(Float)

    wards_placed_window: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    wards_cleared_window: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deaths_window: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    setup_score: Mapped[float | None] = mapped_column(Float)

    __table_args__ = (
        Index("ix_obj_setup_match_puuid", "match_id", "puuid"),
        Index("ix_obj_setup_type", "objective_type"),
    )


class CohortStat(Base):
    """A peer baseline, materialised at several specificities.

    `specificity` records how many dimensions the cohort pins down, so a lookup
    can start at the most specific cohort that has enough samples and fall back.
    """

    __tablename__ = "cohort_stats"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    cohort_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    dimensions: Mapped[dict[str, Any]] = mapped_column(JSONVariant, nullable=False, default=dict)
    specificity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    metric: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    n: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    mean: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    std: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    p10: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    p25: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    p50: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    p75: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    p90: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    computed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("cohort_key", "metric", name="uq_cohort_metric"),
        Index("ix_cohort_metric_spec", "metric", "specificity"),
    )


class MapRiskCell(Base):
    """Empirical death risk for one cell of the map, by phase, role and rank.

    Every timeline frame is an exposure labelled with whether a death followed
    within `horizon_seconds`; `risk` is deaths over exposures, and `lift` is that
    against the baseline for the same phase.
    """

    __tablename__ = "map_risk_cells"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    grid_size: Mapped[int] = mapped_column(Integer, nullable=False)
    cell_x: Mapped[int] = mapped_column(Integer, nullable=False)
    cell_y: Mapped[int] = mapped_column(Integer, nullable=False)
    phase: Mapped[str] = mapped_column(String(8), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    tier_group: Mapped[str] = mapped_column(String(16), nullable=False)
    horizon_seconds: Mapped[int] = mapped_column(Integer, nullable=False)

    exposures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deaths: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    risk: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    baseline_risk: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    lift: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    #: Coarse human-readable label for the cell, for rendering only.
    zone: Mapped[str | None] = mapped_column(String(24))
    computed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint(
            "grid_size", "cell_x", "cell_y", "phase", "role", "tier_group",
            "horizon_seconds", name="uq_risk_cell",
        ),
        Index("ix_risk_lookup", "phase", "role", "tier_group"),
    )


# ---------------------------------------------------------------------------
# Operational
# ---------------------------------------------------------------------------


class IngestJob(Base, TimestampMixin):
    __tablename__ = "ingest_jobs"

    #: A UUID4 string. Generated here because callers create a job by
    #: describing the work, never by naming it.
    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    puuid: Mapped[str] = mapped_column(String(78), nullable=False, index=True)
    platform: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=JobStatus.PENDING)

    requested_matches: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    matches_discovered: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    matches_ingested: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    matches_skipped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    timelines_ingested: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    features_computed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    error: Mapped[str | None] = mapped_column(Text)
    stats: Mapped[dict[str, Any]] = mapped_column(JSONVariant, nullable=False, default=dict)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @property
    def progress(self) -> float:
        """Fraction of the requested work completed, in [0, 1].

        Skipped matches count as done: one already in the database is not
        outstanding work, and a job that skips everything is finished rather
        than stuck at zero. A job in a terminal state reports 1.0 even when it
        ingested fewer matches than asked for, because nothing further happens.
        """
        if self.status in (JobStatus.SUCCEEDED, JobStatus.PARTIAL, JobStatus.FAILED):
            return 1.0
        if not self.requested_matches:
            return 0.0
        done = self.matches_ingested + self.matches_skipped
        return min(1.0, done / self.requested_matches)


class MLModelRecord(Base, TimestampMixin):
    """A trained model's provenance.

    The artifact lives on disk; this row is what makes a served number
    explicable later - which model, trained on how many samples, and what it
    leaned on.
    """

    __tablename__ = "ml_models"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    artifact_path: Mapped[str | None] = mapped_column(String(512))

    params: Mapped[dict[str, Any]] = mapped_column(JSONVariant, nullable=False, default=dict)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONVariant, nullable=False, default=dict)
    feature_importances: Mapped[dict[str, Any]] = mapped_column(
        JSONVariant, nullable=False, default=dict
    )
    feature_names: Mapped[list[str]] = mapped_column(JSONVariant, nullable=False, default=list)
    n_samples: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    trained_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (UniqueConstraint("name", "version", name="uq_model_name_version"),)


__all__ = [
    "Base",
    "CohortStat",
    "IngestJob",
    "JobStatus",
    "LeagueEntry",
    "MLModelRecord",
    "MapRiskCell",
    "Match",
    "MatchParticipant",
    "MatchTeam",
    "ObjectiveSetup",
    "ParticipantFeatures",
    "RoamEvent",
    "Summoner",
    "TimelineEvent",
    "TimelineFrame",
]

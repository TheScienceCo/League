"""Feature engineering, on hand-built matches with known answers.

These use synthetic fixtures rather than the simulator so the expected values can
be computed by hand — the point is to pin the arithmetic, not to observe it.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.db.models import (
    Match,
    MatchParticipant,
    MatchTeam,
    TimelineEvent,
    TimelineFrame,
)
from app.services.analytics.context import MatchContext
from app.services.analytics.features import FeatureBuilder, compute_and_store_features

MATCH_ID = "TEST_0001"


def _build_match(db, duration_seconds: int = 30 * 60) -> None:  # type: ignore[no-untyped-def]
    """Two mid laners, one clearly ahead, plus filler to make ten players."""
    db.add(
        Match(
            match_id=MATCH_ID,
            platform="na1",
            region="americas",
            queue_id=420,
            patch="14.19",
            game_version="14.19.1.1",
            game_start=datetime.now(UTC),
            game_duration_seconds=duration_seconds,
            winning_team_id=100,
            timeline_ingested=True,
        )
    )
    for team_id in (100, 200):
        db.add(MatchTeam(match_id=MATCH_ID, team_id=team_id, win=team_id == 100))

    roles = ["MIDDLE", "TOP", "JUNGLE", "BOTTOM", "UTILITY"]
    pid = 1
    for team_id in (100, 200):
        for role in roles:
            is_hero = pid == 1
            is_rival = pid == 6
            db.add(
                MatchParticipant(
                    match_id=MATCH_ID,
                    puuid=f"p{pid}",
                    participant_id=pid,
                    team_id=team_id,
                    win=team_id == 100,
                    champion_id=100 + pid,
                    champion_name=f"Champ{pid}",
                    team_position=role,
                    kills=6 if is_hero else 2,
                    deaths=2 if is_hero else 4,
                    assists=4 if is_hero else 3,
                    gold_earned=15000 if is_hero else 10000,
                    total_minions_killed=240 if is_hero else 150,
                    neutral_minions_killed=0,
                    total_damage_to_champions=30000 if is_hero else 15000,
                    total_damage_taken=20000,
                    vision_score=30 if is_hero else 15,
                    wards_placed=15 if is_hero else 6,
                    wards_killed=6 if is_hero else 2,
                    detector_wards_placed=3 if is_hero else 1,
                    rank_tier="PLATINUM",
                    tier_group="PLAT_EMERALD",
                )
            )
            pid += 1
            del is_rival

    # Frames: the hero out-earns their lane opponent by a fixed amount per minute.
    for minute in range(0, duration_seconds // 60 + 1):
        for participant in range(1, 11):
            hero = participant == 1
            rival = participant == 6
            gold = 500 + minute * (350 if hero else 300)
            xp = minute * (480 if hero else 420)
            cs = minute * (8 if hero else 6)
            if not hero and not rival:
                gold, xp, cs = 500 + minute * 300, minute * 400, minute * 5
            db.add(
                TimelineFrame(
                    match_id=MATCH_ID,
                    participant_id=participant,
                    timestamp_ms=minute * 60_000,
                    minute=minute,
                    total_gold=gold,
                    current_gold=int(gold * 0.2),
                    xp=xp,
                    level=min(18, 1 + minute // 2),
                    minions_killed=cs,
                    jungle_minions_killed=0,
                    position_x=7500.0,
                    position_y=7500.0,
                    damage_done_to_champions=minute * (900 if hero else 450),
                    damage_taken=minute * 600,
                )
            )
    db.flush()


def _add_kill(db, ts_ms: int, killer: int, victim: int, assists: list[int]) -> None:  # type: ignore[no-untyped-def]
    db.add(
        TimelineEvent(
            match_id=MATCH_ID,
            timestamp_ms=ts_ms,
            minute=ts_ms // 60_000,
            type="CHAMPION_KILL",
            killer_id=killer,
            victim_id=victim,
            assisting_participant_ids=assists,
            position_x=7500.0,
            position_y=7500.0,
            raw={},
        )
    )


def test_lane_differentials_use_the_lane_opponent(db) -> None:  # type: ignore[no-untyped-def]
    _build_match(db)
    ctx = MatchContext.load(db, MATCH_ID)
    assert ctx is not None
    row = FeatureBuilder(ctx).build(ctx.by_pid[1])

    # 50 gold/min more than the rival, for ten and fifteen minutes.
    assert row["gold_diff_10"] == pytest.approx(500.0)
    assert row["gold_diff_15"] == pytest.approx(750.0)
    assert row["xp_diff_10"] == pytest.approx(600.0)
    assert row["cs_diff_10"] == pytest.approx(20.0)
    assert row["cs_per_min"] == pytest.approx(240 / 30)


def test_lane_opponent_pairing_is_by_role(db) -> None:  # type: ignore[no-untyped-def]
    _build_match(db)
    ctx = MatchContext.load(db, MATCH_ID)
    assert ctx is not None
    assert ctx.lane_opponents[1] == 6  # both MIDDLE, opposite teams
    assert ctx.lane_opponents[6] == 1


def test_differentials_are_none_when_the_game_is_too_short(db) -> None:  # type: ignore[no-untyped-def]
    """A nine-minute game has no ten-minute mark, and we do not invent one."""
    _build_match(db, duration_seconds=9 * 60)
    ctx = MatchContext.load(db, MATCH_ID)
    assert ctx is not None
    row = FeatureBuilder(ctx).build(ctx.by_pid[1])
    assert row["gold_diff_10"] is None
    assert row["gold_diff_15"] is None


def test_shares_and_rce(db) -> None:  # type: ignore[no-untyped-def]
    _build_match(db)
    ctx = MatchContext.load(db, MATCH_ID)
    assert ctx is not None
    row = FeatureBuilder(ctx).build(ctx.by_pid[1])

    # Team 100: hero 30000 damage of (30000 + 4*15000) = 90000 total.
    assert row["damage_share"] == pytest.approx(30000 / 90000)
    # Gold: 15000 of (15000 + 4*10000) = 55000.
    assert row["gold_share"] == pytest.approx(15000 / 55000)
    assert row["rce_raw"] == pytest.approx((30000 / 90000) / (15000 / 55000))
    assert row["damage_per_gold"] == pytest.approx(2.0)
    # RCE above 1 means output share exceeded resource share.
    assert row["rce_raw"] > 1.0


def test_kill_participation_uses_team_kills(db) -> None:  # type: ignore[no-untyped-def]
    _build_match(db)
    ctx = MatchContext.load(db, MATCH_ID)
    assert ctx is not None
    row = FeatureBuilder(ctx).build(ctx.by_pid[1])
    team_kills = 6 + 2 * 4  # hero + four teammates
    assert row["kill_participation"] == pytest.approx((6 + 4) / team_kills)


def test_solo_kills_and_early_deaths_come_from_events(db) -> None:  # type: ignore[no-untyped-def]
    _build_match(db)
    _add_kill(db, 4 * 60_000, killer=1, victim=6, assists=[])  # solo kill
    _add_kill(db, 8 * 60_000, killer=1, victim=7, assists=[2, 3])  # assisted
    _add_kill(db, 6 * 60_000, killer=6, victim=1, assists=[])  # solo death, early
    _add_kill(db, 20 * 60_000, killer=7, victim=1, assists=[8])  # late death
    db.flush()

    ctx = MatchContext.load(db, MATCH_ID)
    assert ctx is not None
    row = FeatureBuilder(ctx).build(ctx.by_pid[1])

    assert row["solo_kills"] == 1
    assert row["solo_deaths"] == 1
    assert row["solo_kill_diff"] == 0
    # Only the death at minute six is before the ten-minute cutoff.
    assert row["early_deaths"] == 1


def test_objective_participation_counts_credit_and_proximity(db) -> None:  # type: ignore[no-untyped-def]
    from app.core.constants import DRAGON_PIT

    _build_match(db)
    # Two dragons for team 100: the hero is credited on one, and merely present
    # for the other (frames put everyone at mid, far from the pit).
    db.add(
        TimelineEvent(
            match_id=MATCH_ID,
            timestamp_ms=10 * 60_000,
            minute=10,
            type="ELITE_MONSTER_KILL",
            killer_id=1,
            assisting_participant_ids=[2],
            monster_type="DRAGON",
            position_x=DRAGON_PIT[0],
            position_y=DRAGON_PIT[1],
            raw={"killerTeamId": 100},
        )
    )
    db.add(
        TimelineEvent(
            match_id=MATCH_ID,
            timestamp_ms=20 * 60_000,
            minute=20,
            type="ELITE_MONSTER_KILL",
            killer_id=3,
            assisting_participant_ids=[],
            monster_type="DRAGON",
            position_x=DRAGON_PIT[0],
            position_y=DRAGON_PIT[1],
            raw={"killerTeamId": 100},
        )
    )
    db.flush()

    ctx = MatchContext.load(db, MATCH_ID)
    assert ctx is not None
    row = FeatureBuilder(ctx).build(ctx.by_pid[1])
    # Credited on one of two team dragons; not near the pit for the other.
    assert row["objective_participation"] == pytest.approx(0.5)
    assert row["dragon_participation"] == pytest.approx(0.5)


def test_lead_conversion_flags(db) -> None:  # type: ignore[no-untyped-def]
    _build_match(db)
    ctx = MatchContext.load(db, MATCH_ID)
    assert ctx is not None
    row = FeatureBuilder(ctx).build(ctx.by_pid[1])
    # Team 100 leads by 15 * 50 = 750 gold at minute 15, under the 1000 threshold.
    assert row["had_lead_at_15"] is False
    assert row["converted_lead"] is False


def test_compute_and_store_is_idempotent(db) -> None:  # type: ignore[no-untyped-def]
    from app.db.models import ParticipantFeatures

    _build_match(db)
    assert compute_and_store_features(db, MATCH_ID) == 10
    assert compute_and_store_features(db, MATCH_ID) == 10
    assert db.query(ParticipantFeatures).count() == 10
    assert db.get(Match, MATCH_ID).features_computed is True

"""Idempotent writers from Riot DTOs into the normalized schema.

Every function here is safe to re-run: matches are keyed by `match_id`, frames
by `(match, participant, timestamp)`, and league entries by `(puuid, queue)`.
Re-ingesting a match replaces its timeline rather than duplicating it.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

from app.core.constants import (
    parse_patch,
    region_for_platform,
    tier_group,
    tier_rank_score,
)
from app.db.models import (
    LeagueEntry,
    Match,
    MatchParticipant,
    MatchTeam,
    Summoner,
    TimelineEvent,
    TimelineFrame,
)
from app.services.riot.dto import (
    AccountDTO,
    LeagueEntryDTO,
    MatchDTO,
    SummonerDTO,
    TimelineDTO,
)


def _ms_to_dt(value: int | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromtimestamp(value / 1000.0, tz=UTC)


def upsert_summoner(
    session: Session,
    account: AccountDTO,
    summoner: SummonerDTO | None,
    platform: str,
) -> Summoner:
    row = session.get(Summoner, account.puuid)
    if row is None:
        row = Summoner(puuid=account.puuid, platform=platform.lower())
        session.add(row)
    row.game_name = account.game_name or row.game_name
    row.tag_line = account.tag_line or row.tag_line
    row.platform = platform.lower()
    if summoner is not None:
        row.summoner_id = summoner.id or row.summoner_id
        row.account_id = summoner.account_id or row.account_id
        row.profile_icon_id = summoner.profile_icon_id
        row.summoner_level = summoner.summoner_level
        row.revision_date = _ms_to_dt(summoner.revision_date)
    session.flush()
    return row


def upsert_league_entries(
    session: Session, puuid: str, entries: list[LeagueEntryDTO]
) -> list[LeagueEntry]:
    """Replace the stored standings for the queues present in `entries`.

    Queues absent from the payload are left alone — Riot omits queues a player is
    not placed in, and we would rather keep a stale flex rank than delete it.
    """
    out: list[LeagueEntry] = []
    now = datetime.now(UTC)
    for dto in entries:
        row = session.scalar(
            select(LeagueEntry).where(
                LeagueEntry.puuid == puuid, LeagueEntry.queue_type == dto.queue_type
            )
        )
        if row is None:
            row = LeagueEntry(puuid=puuid, queue_type=dto.queue_type)
            session.add(row)
        row.tier = dto.tier
        row.division = dto.division
        row.league_points = dto.league_points
        row.wins = dto.wins
        row.losses = dto.losses
        row.hot_streak = dto.hot_streak
        row.veteran = dto.veteran
        row.inactive = dto.inactive
        row.fresh_blood = dto.fresh_blood
        row.rank_score = tier_rank_score(dto.tier, dto.division, dto.league_points)
        row.snapshot_at = now
        out.append(row)
    session.flush()
    return out


def solo_queue_rank(session: Session, puuid: str) -> tuple[str | None, str | None, float]:
    """Ranked-solo standing for a player, or `(None, None, 0.0)` if unknown."""
    row = session.scalar(
        select(LeagueEntry).where(
            LeagueEntry.puuid == puuid, LeagueEntry.queue_type == "RANKED_SOLO_5x5"
        )
    )
    if row is None:
        return None, None, 0.0
    return row.tier, row.division, row.rank_score


def persist_match(
    session: Session,
    dto: MatchDTO,
    *,
    platform: str,
    data_source: str = "riot",
) -> Match:
    """Insert or refresh a match and all of its participants and teams."""
    info = dto.info
    match_id = dto.metadata.match_id
    match = session.get(Match, match_id)
    if match is None:
        match = Match(match_id=match_id)
        session.add(match)

    platform_id = (info.platform_id or platform).lower()
    match.platform = platform_id
    match.region = region_for_platform(platform_id if platform_id in _KNOWN else platform)
    match.queue_id = info.queue_id
    match.game_mode = info.game_mode
    match.game_type = info.game_type
    match.map_id = info.map_id
    match.game_version = info.game_version
    match.patch = parse_patch(info.game_version)
    match.game_creation = _ms_to_dt(info.game_creation)
    match.game_start = _ms_to_dt(info.game_start_timestamp)
    match.game_end = _ms_to_dt(info.game_end_timestamp)
    match.game_duration_seconds = _normalise_duration(info.game_duration)
    match.data_source = data_source

    winning = next((t.team_id for t in info.teams if t.win), None)
    match.winning_team_id = winning
    session.flush()

    session.execute(delete(MatchTeam).where(MatchTeam.match_id == match_id))
    for team in info.teams:
        obj = team.objectives
        session.add(
            MatchTeam(
                match_id=match_id,
                team_id=team.team_id,
                win=team.win,
                champion_kills=obj.champion.kills,
                dragon_kills=obj.dragon.kills,
                baron_kills=obj.baron.kills,
                herald_kills=obj.rift_herald.kills,
                tower_kills=obj.tower.kills,
                inhibitor_kills=obj.inhibitor.kills,
                first_blood=obj.champion.first,
                first_tower=obj.tower.first,
                first_dragon=obj.dragon.first,
                first_baron=obj.baron.first,
                bans=[b.get("championId") for b in team.bans],
            )
        )

    session.execute(delete(MatchParticipant).where(MatchParticipant.match_id == match_id))
    for p in info.participants:
        tier, division, score = solo_queue_rank(session, p.puuid)
        session.add(
            MatchParticipant(
                match_id=match_id,
                puuid=p.puuid,
                participant_id=p.participant_id,
                team_id=p.team_id,
                win=p.win,
                riot_id_game_name=p.riot_id_game_name,
                riot_id_tagline=p.riot_id_tagline,
                champion_id=p.champion_id,
                champion_name=p.champion_name,
                champ_level=p.champ_level,
                team_position=p.position or "UNKNOWN",
                individual_position=p.individual_position,
                lane=p.lane,
                kills=p.kills,
                deaths=p.deaths,
                assists=p.assists,
                gold_earned=p.gold_earned,
                gold_spent=p.gold_spent,
                total_minions_killed=p.total_minions_killed,
                neutral_minions_killed=p.neutral_minions_killed,
                total_damage_to_champions=p.total_damage_dealt_to_champions,
                physical_damage_to_champions=p.physical_damage_dealt_to_champions,
                magic_damage_to_champions=p.magic_damage_dealt_to_champions,
                true_damage_to_champions=p.true_damage_dealt_to_champions,
                total_damage_taken=p.total_damage_taken,
                damage_self_mitigated=p.damage_self_mitigated,
                total_heals_on_teammates=p.total_heals_on_teammates,
                damage_dealt_to_objectives=p.damage_dealt_to_objectives,
                damage_dealt_to_turrets=p.damage_dealt_to_turrets,
                vision_score=p.vision_score,
                wards_placed=p.wards_placed,
                wards_killed=p.wards_killed,
                detector_wards_placed=p.detector_wards_placed,
                vision_wards_bought=p.vision_wards_bought_in_game,
                turret_takedowns=p.turret_takedowns,
                dragon_takedowns=p.dragon_kills,
                baron_takedowns=p.baron_kills,
                objectives_stolen=p.objectives_stolen,
                time_ccing_others=p.time_ccing_others,
                total_time_spent_dead=p.total_time_spent_dead,
                longest_time_spent_living=p.longest_time_spent_living,
                first_blood_kill=p.first_blood_kill,
                first_tower_kill=p.first_tower_kill,
                summoner_spell_1=p.summoner1_id,
                summoner_spell_2=p.summoner2_id,
                items=p.items,
                perks=p.perks,
                rank_tier=tier,
                rank_division=division,
                rank_score=score,
                tier_group=tier_group(tier),
            )
        )
    session.flush()
    return match


_KNOWN = {
    "na1",
    "br1",
    "la1",
    "la2",
    "euw1",
    "eun1",
    "tr1",
    "ru",
    "me1",
    "kr",
    "jp1",
    "tw2",
    "sg2",
    "vn2",
    "oc1",
    "ph2",
    "th2",
}


def _normalise_duration(raw: int) -> int:
    """Riot reported durations in ms for a period around patch 11.20.

    Values that large are unambiguous (no game runs 10^5 seconds), so we can
    safely normalise rather than trusting the field blindly.
    """
    return raw // 1000 if raw > 100_000 else raw


def persist_timeline(session: Session, timeline: TimelineDTO, *, match_id: str) -> tuple[int, int]:
    """Replace the stored timeline for a match. Returns (frames, events) written."""
    session.execute(delete(TimelineFrame).where(TimelineFrame.match_id == match_id))
    session.execute(delete(TimelineEvent).where(TimelineEvent.match_id == match_id))

    frame_rows: list[dict[str, object]] = []
    event_rows: list[dict[str, object]] = []
    seen_events: set[tuple[int, str, int | None, int | None]] = set()
    #: (participant, timestamp) pairs already written. Riot payloads occasionally
    #: repeat a frame boundary; the table's unique constraint would reject the
    #: whole batch, so we drop the repeat instead of failing the match.
    seen_frames: set[tuple[int, int]] = set()

    for frame in timeline.info.frames:
        minute = frame.timestamp // 60_000
        for pf in frame.participant_frames.values():
            frame_key = (pf.participant_id, frame.timestamp)
            if frame_key in seen_frames:
                continue
            seen_frames.add(frame_key)
            pos = pf.position
            dmg = pf.damage_stats
            frame_rows.append(
                {
                    "match_id": match_id,
                    "participant_id": pf.participant_id,
                    "timestamp_ms": frame.timestamp,
                    "minute": minute,
                    "total_gold": pf.total_gold,
                    "current_gold": pf.current_gold,
                    "xp": pf.xp,
                    "level": pf.level,
                    "minions_killed": pf.minions_killed,
                    "jungle_minions_killed": pf.jungle_minions_killed,
                    "time_enemy_spent_controlled": pf.time_enemy_spent_controlled,
                    "position_x": float(pos.x) if pos else None,
                    "position_y": float(pos.y) if pos else None,
                    "damage_done_to_champions": dmg.total_damage_done_to_champions if dmg else 0,
                    "damage_taken": dmg.total_damage_taken if dmg else 0,
                }
            )
        for event in frame.events:
            # The last frame repeats trailing events in some payloads; dedupe on
            # the natural key rather than trusting frame membership.
            key = (event.timestamp, event.type, event.participant_id, event.victim_id)
            if key in seen_events:
                continue
            seen_events.add(key)
            pos = event.position
            event_rows.append(
                {
                    "match_id": match_id,
                    "timestamp_ms": event.timestamp,
                    "minute": event.timestamp // 60_000,
                    "type": event.type,
                    "participant_id": event.participant_id,
                    "killer_id": event.killer_id,
                    "victim_id": event.victim_id,
                    "assisting_participant_ids": list(event.assisting_participant_ids),
                    "team_id": event.team_id,
                    "position_x": float(pos.x) if pos else None,
                    "position_y": float(pos.y) if pos else None,
                    "monster_type": event.monster_type,
                    "monster_sub_type": event.monster_sub_type,
                    "building_type": event.building_type,
                    "tower_type": event.tower_type,
                    "lane_type": event.lane_type,
                    "ward_type": event.ward_type,
                    "creator_id": event.creator_id,
                    "item_id": event.item_id,
                    "kill_type": event.kill_type,
                    "bounty": event.bounty,
                    "shutdown_bounty": event.shutdown_bounty,
                    "raw": event.model_dump(mode="json", by_alias=True, exclude_none=True),
                }
            )

    # Frames are the bulk of the write volume; a single executemany is worth it.
    if frame_rows:
        session.execute(insert(TimelineFrame), frame_rows)
    if event_rows:
        session.execute(insert(TimelineEvent), event_rows)

    match = session.get(Match, match_id)
    if match is not None:
        match.timeline_ingested = True
    session.flush()
    return len(frame_rows), len(event_rows)


def backfill_participant_ranks(session: Session, match_id: str) -> int:
    """Re-apply known ranks to a match's participants.

    Ranks are learned incrementally: a player we ingest later tells us the rank
    of games they appeared in earlier. Cheap to re-run and it materially improves
    cohort quality over time.
    """
    updated = 0
    for row in session.scalars(
        select(MatchParticipant).where(MatchParticipant.match_id == match_id)
    ):
        tier, division, score = solo_queue_rank(session, row.puuid)
        if tier and row.rank_tier != tier:
            row.rank_tier = tier
            row.rank_division = division
            row.rank_score = score
            row.tier_group = tier_group(tier)
            updated += 1
    session.flush()
    return updated


__all__ = [
    "backfill_participant_ranks",
    "persist_match",
    "persist_timeline",
    "solo_queue_rank",
    "upsert_league_entries",
    "upsert_summoner",
]

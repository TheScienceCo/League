"""`MatchContext` — one loaded match, indexed for analysis.

Every analyzer (features, objectives, roams, spatial, DVA) needs the same
handful of joins: participant by id, frames by participant and minute, events by
type, team totals. Loading that once and passing it around keeps each analyzer a
pure function of the context and avoids N+1 queries.
"""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass, field
from functools import cached_property

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import Role, duration_bucket
from app.db.models import (
    Match,
    MatchParticipant,
    MatchTeam,
    TimelineEvent,
    TimelineFrame,
)

Point = tuple[float, float]


@dataclass
class MatchContext:
    match: Match
    participants: list[MatchParticipant]
    teams: dict[int, MatchTeam]
    frames: dict[int, list[TimelineFrame]] = field(default_factory=dict)
    events: list[TimelineEvent] = field(default_factory=list)

    # --- loading ---------------------------------------------------------

    @classmethod
    def load(cls, session: Session, match_id: str) -> MatchContext | None:
        match = session.get(Match, match_id)
        if match is None:
            return None
        participants = list(
            session.scalars(
                select(MatchParticipant)
                .where(MatchParticipant.match_id == match_id)
                .order_by(MatchParticipant.participant_id)
            )
        )
        teams = {
            t.team_id: t
            for t in session.scalars(select(MatchTeam).where(MatchTeam.match_id == match_id))
        }
        frames: dict[int, list[TimelineFrame]] = {}
        for frame in session.scalars(
            select(TimelineFrame)
            .where(TimelineFrame.match_id == match_id)
            .order_by(TimelineFrame.participant_id, TimelineFrame.timestamp_ms)
        ):
            frames.setdefault(frame.participant_id, []).append(frame)
        events = list(
            session.scalars(
                select(TimelineEvent)
                .where(TimelineEvent.match_id == match_id)
                .order_by(TimelineEvent.timestamp_ms)
            )
        )
        return cls(
            match=match, participants=participants, teams=teams, frames=frames, events=events
        )

    # --- indexes ---------------------------------------------------------

    @cached_property
    def by_pid(self) -> dict[int, MatchParticipant]:
        return {p.participant_id: p for p in self.participants}

    @cached_property
    def by_puuid(self) -> dict[str, MatchParticipant]:
        return {p.puuid: p for p in self.participants}

    @cached_property
    def events_by_type(self) -> dict[str, list[TimelineEvent]]:
        out: dict[str, list[TimelineEvent]] = {}
        for e in self.events:
            out.setdefault(e.type, []).append(e)
        return out

    @cached_property
    def _frame_times(self) -> dict[int, list[int]]:
        return {pid: [f.timestamp_ms for f in fs] for pid, fs in self.frames.items()}

    @cached_property
    def duration_minutes(self) -> float:
        return max(self.match.game_duration_seconds / 60.0, 1e-6)

    @cached_property
    def duration_bucket(self) -> str:
        return duration_bucket(self.match.game_duration_seconds)

    @property
    def has_timeline(self) -> bool:
        return bool(self.frames)

    # --- team aggregates -------------------------------------------------

    @cached_property
    def team_kills(self) -> dict[int, int]:
        out = {100: 0, 200: 0}
        for p in self.participants:
            out[p.team_id] = out.get(p.team_id, 0) + p.kills
        return out

    @cached_property
    def team_damage(self) -> dict[int, int]:
        out: dict[int, int] = {}
        for p in self.participants:
            out[p.team_id] = out.get(p.team_id, 0) + p.total_damage_to_champions
        return out

    @cached_property
    def team_gold(self) -> dict[int, int]:
        out: dict[int, int] = {}
        for p in self.participants:
            out[p.team_id] = out.get(p.team_id, 0) + p.gold_earned
        return out

    @cached_property
    def team_damage_taken(self) -> dict[int, int]:
        out: dict[int, int] = {}
        for p in self.participants:
            out[p.team_id] = out.get(p.team_id, 0) + p.total_damage_taken
        return out

    def teammates(self, pid: int) -> list[MatchParticipant]:
        me = self.by_pid[pid]
        return [p for p in self.participants if p.team_id == me.team_id and p.participant_id != pid]

    def opponents(self, pid: int) -> list[MatchParticipant]:
        me = self.by_pid[pid]
        return [p for p in self.participants if p.team_id != me.team_id]

    @cached_property
    def lane_opponents(self) -> dict[int, int]:
        """Participant id -> the opposing player in the same role.

        Uses Riot's `teamPosition`. When a game has no position data (remakes,
        odd queues) or the roles do not pair up 1:1, the player simply has no
        opponent and all the `*_diff` features are left null rather than being
        computed against an arbitrary player.
        """
        out: dict[int, int] = {}
        by_role: dict[tuple[int, str], list[int]] = {}
        for p in self.participants:
            if p.team_position in {"", "UNKNOWN", None}:
                continue
            by_role.setdefault((p.team_id, p.team_position), []).append(p.participant_id)
        for (team_id, role), pids in by_role.items():
            other = by_role.get((200 if team_id == 100 else 100, role), [])
            if len(pids) == 1 and len(other) == 1:
                out[pids[0]] = other[0]
        return out

    # --- frame access ----------------------------------------------------

    def frame_at_minute(self, pid: int, minute: int) -> TimelineFrame | None:
        """The frame stamped exactly at `minute` (Riot emits one per minute)."""
        for f in self.frames.get(pid, []):
            if f.minute == minute:
                return f
        return None

    def frame_before(self, pid: int, timestamp_ms: int) -> TimelineFrame | None:
        times = self._frame_times.get(pid)
        if not times:
            return None
        idx = bisect_left(times, timestamp_ms)
        if idx < len(times) and times[idx] == timestamp_ms:
            return self.frames[pid][idx]
        return self.frames[pid][idx - 1] if idx > 0 else None

    def position_at(self, pid: int, timestamp_ms: int) -> Point | None:
        """Estimated position at an arbitrary timestamp.

        Riot samples positions once per minute, so any sub-minute query is a
        linear interpolation between the bracketing frames. It is an estimate,
        and every metric built on it (objective arrival timing, roam windows) is
        labelled as such in the API.
        """
        fs = self.frames.get(pid)
        times = self._frame_times.get(pid)
        if not fs or not times:
            return None

        def point(frame: TimelineFrame) -> Point | None:
            # A frame carries both coordinates or neither; treating a half-filled
            # one as a position would silently place the player at y=0.
            if frame.position_x is None or frame.position_y is None:
                return None
            return (frame.position_x, frame.position_y)

        idx = bisect_left(times, timestamp_ms)
        if idx == 0:
            return point(fs[0])
        if idx >= len(fs):
            return point(fs[-1])

        start, end = point(fs[idx - 1]), point(fs[idx])
        if start is None or end is None:
            return start or end
        span = fs[idx].timestamp_ms - fs[idx - 1].timestamp_ms
        t = 0.0 if span <= 0 else (timestamp_ms - fs[idx - 1].timestamp_ms) / span
        return (
            start[0] + t * (end[0] - start[0]),
            start[1] + t * (end[1] - start[1]),
        )

    def team_gold_at(self, team_id: int, minute: int) -> int | None:
        total = 0
        found = False
        for p in self.participants:
            if p.team_id != team_id:
                continue
            f = self.frame_at_minute(p.participant_id, minute)
            if f is not None:
                total += f.total_gold
                found = True
        return total if found else None

    def team_gold_diff_at(self, team_id: int, minute: int) -> float | None:
        mine = self.team_gold_at(team_id, minute)
        theirs = self.team_gold_at(200 if team_id == 100 else 100, minute)
        if mine is None or theirs is None:
            return None
        return float(mine - theirs)

    def role_of(self, pid: int) -> Role:
        p = self.by_pid.get(pid)
        if p is None:
            return Role.UNKNOWN
        try:
            return Role(p.team_position)
        except ValueError:
            return Role.UNKNOWN

    # --- event helpers ---------------------------------------------------

    def kills_by(self, pid: int) -> list[TimelineEvent]:
        return [e for e in self.events_by_type.get("CHAMPION_KILL", []) if e.killer_id == pid]

    def deaths_of(self, pid: int) -> list[TimelineEvent]:
        return [e for e in self.events_by_type.get("CHAMPION_KILL", []) if e.victim_id == pid]

    @staticmethod
    def assists_of(event: TimelineEvent) -> list[int]:
        raw = event.assisting_participant_ids
        return [int(x) for x in raw] if isinstance(raw, list) else []

    def took_part(self, event: TimelineEvent, pid: int) -> bool:
        return event.killer_id == pid or pid in self.assists_of(event)

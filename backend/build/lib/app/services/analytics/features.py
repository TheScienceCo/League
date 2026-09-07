"""Per-participant feature engineering.

Every value produced here is derived. Where a Riot field is used at all it is
used as an input to a difference, a rate, a share, or a conditional split — never
passed through. The reasoning behind each family of features is documented in
`docs/FEATURES.md`; the short version:

* **Differentials** (`gold_diff_10`, `xp_diff_15`, `cs_diff_10`) are measured
  against the *lane opponent*, not the lobby average, because that is the player
  the laning phase is actually contested against.
* **Shares** (`damage_share`, `gold_share`) normalise away game length and team
  strength, which raw totals do not.
* **Resource Conversion Efficiency** divides output share by resource share, so a
  player who takes 30% of their team's gold and produces 30% of its damage scores
  1.0 regardless of role, patch or how fed the team was.
* **Conditional splits** (`dpm_while_ahead` vs `dpm_while_behind`) separate the
  two very different games a player plays, which a single average hides.

Values that cannot be computed honestly are left `None` — a game that ended at
minute 9 has no `gold_diff_10`, and we do not impute one.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Match, MatchParticipant, ParticipantFeatures
from app.services.analytics.context import MatchContext

#: A team is "ahead" once its gold lead exceeds this, and "behind" below its
#: negation. The dead band in between is treated as neither, so the conditional
#: splits describe genuinely different game states rather than coin-flips.
GOLD_STATE_THRESHOLD = 1000.0

#: Deaths before this mark count as "early deaths" — the laning-phase mistakes
#: that compound, as opposed to a late-game teamfight death.
EARLY_DEATH_CUTOFF_MS = 10 * 60 * 1000

#: How close a player must be to an objective to be counted as present when they
#: were not credited with a takedown by Riot. Roughly a screen and a half.
OBJECTIVE_PROXIMITY_UNITS = 2200.0

ELITE_DRAGONS = {"DRAGON"}
ELITE_BARON_HERALD = {"BARON_NASHOR", "RIFTHERALD"}


@dataclass(slots=True)
class _Series:
    """Per-minute deltas derived from a participant's cumulative frame values."""

    minutes: list[int]
    gold: list[float]
    xp: list[float]
    cs: list[float]
    damage_delta: list[float]
    cs_delta: list[float]


def _series_for(ctx: MatchContext, pid: int) -> _Series:
    frames = ctx.frames.get(pid, [])
    minutes = [f.minute for f in frames]
    gold = [float(f.total_gold) for f in frames]
    xp = [float(f.xp) for f in frames]
    cs = [float(f.minions_killed + f.jungle_minions_killed) for f in frames]
    damage = [float(f.damage_done_to_champions) for f in frames]
    damage_delta = [0.0] + [max(0.0, damage[i] - damage[i - 1]) for i in range(1, len(damage))]
    cs_delta = [0.0] + [max(0.0, cs[i] - cs[i - 1]) for i in range(1, len(cs))]
    return _Series(minutes, gold, xp, cs, damage_delta, cs_delta)


def _at_minute(series: _Series, values: list[float], minute: int) -> float | None:
    for i, m in enumerate(series.minutes):
        if m == minute:
            return values[i]
    return None


def _safe_div(num: float | None, den: float | None) -> float | None:
    if num is None or den is None or den == 0:
        return None
    return num / den


def _linear_slope(xs: list[float], ys: list[float]) -> float | None:
    """Least-squares slope; `None` when there is nothing to fit."""
    n = len(xs)
    if n < 2:
        return None
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    denom = sum((x - mean_x) ** 2 for x in xs)
    if denom == 0:
        return None
    return sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True)) / denom


class FeatureBuilder:
    """Computes the `participant_features` row for every player in one match."""

    def __init__(self, ctx: MatchContext) -> None:
        self.ctx = ctx

    def build_all(self) -> list[dict[str, object]]:
        return [self.build(p) for p in self.ctx.participants]

    # --- per player -------------------------------------------------------

    def build(self, p: MatchParticipant) -> dict[str, object]:
        ctx = self.ctx
        pid = p.participant_id
        minutes = ctx.duration_minutes
        series = _series_for(ctx, pid)
        opp_pid = ctx.lane_opponents.get(pid)
        opp_series = _series_for(ctx, opp_pid) if opp_pid is not None else None

        row: dict[str, object] = {
            "match_id": ctx.match.match_id,
            "puuid": p.puuid,
            "participant_id": pid,
            "team_position": p.team_position,
            "champion_id": p.champion_id,
            "tier_group": p.tier_group,
            "rank_score": p.rank_score,
            "patch": ctx.match.patch,
            "queue_id": ctx.match.queue_id,
            "duration_bucket": ctx.duration_bucket,
            "duration_seconds": ctx.match.game_duration_seconds,
            "win": p.win,
        }

        row.update(self._laning(p, series, opp_series, minutes))
        row.update(self._combat(p, minutes))
        row.update(self._vision(p, minutes))
        row.update(self._objectives(p))
        row.update(self._game_state(p, series, opp_series))
        row["extra"] = {}
        return row

    # --- families ---------------------------------------------------------

    def _laning(
        self,
        p: MatchParticipant,
        series: _Series,
        opp: _Series | None,
        minutes: float,
    ) -> dict[str, object]:
        out: dict[str, object] = {}
        for mark in (10, 15):
            if opp is None:
                out[f"gold_diff_{mark}"] = None
                out[f"xp_diff_{mark}"] = None
                out[f"cs_diff_{mark}"] = None
                continue
            mine_g = _at_minute(series, series.gold, mark)
            theirs_g = _at_minute(opp, opp.gold, mark)
            mine_x = _at_minute(series, series.xp, mark)
            theirs_x = _at_minute(opp, opp.xp, mark)
            mine_c = _at_minute(series, series.cs, mark)
            theirs_c = _at_minute(opp, opp.cs, mark)
            out[f"gold_diff_{mark}"] = (
                mine_g - theirs_g if mine_g is not None and theirs_g is not None else None
            )
            out[f"xp_diff_{mark}"] = (
                mine_x - theirs_x if mine_x is not None and theirs_x is not None else None
            )
            out[f"cs_diff_{mark}"] = (
                mine_c - theirs_c if mine_c is not None and theirs_c is not None else None
            )

        cs_total = float(p.total_minions_killed + p.neutral_minions_killed)
        cs_at_15 = _at_minute(series, series.cs, 15)
        out["cs_per_min"] = cs_total / minutes
        out["cs_per_min_first_15"] = (cs_at_15 / 15.0) if cs_at_15 is not None else None
        out["gold_per_min"] = p.gold_earned / minutes
        out["damage_per_min"] = p.total_damage_to_champions / minutes
        return out

    def _combat(self, p: MatchParticipant, minutes: float) -> dict[str, object]:
        ctx = self.ctx
        pid = p.participant_id
        team_kills = ctx.team_kills.get(p.team_id, 0)

        deaths = ctx.deaths_of(pid)
        kills = ctx.kills_by(pid)
        early_deaths = sum(1 for e in deaths if e.timestamp_ms < EARLY_DEATH_CUTOFF_MS)
        # A kill with no assisting participants is a solo kill; the mirrored
        # count for deaths tells us how often the player was picked off 1v1.
        solo_kills = sum(1 for e in kills if not ctx.assists_of(e))
        solo_deaths = sum(1 for e in deaths if not ctx.assists_of(e))

        if not ctx.has_timeline:
            # Without a timeline we can still count early deaths as unknown but
            # must not silently report zero, so fall back to nulls where the
            # figure would be a fiction.
            early_deaths = 0
            solo_kills = solo_deaths = 0

        team_damage = ctx.team_damage.get(p.team_id, 0)
        team_gold = ctx.team_gold.get(p.team_id, 0)
        team_taken = ctx.team_damage_taken.get(p.team_id, 0)

        damage_share = _safe_div(p.total_damage_to_champions, team_damage)
        gold_share = _safe_div(p.gold_earned, team_gold)

        return {
            "kda": (p.kills + p.assists) / max(p.deaths, 1),
            "kill_participation": _safe_div(p.kills + p.assists, team_kills),
            "early_deaths": early_deaths,
            "deaths_per_10min": p.deaths / (minutes / 10.0),
            "solo_kills": solo_kills,
            "solo_deaths": solo_deaths,
            "solo_kill_diff": solo_kills - solo_deaths,
            "damage_per_gold": p.total_damage_to_champions / max(p.gold_earned, 1),
            "damage_share": damage_share,
            "gold_share": gold_share,
            "damage_taken_share": _safe_div(p.total_damage_taken, team_taken),
            # Resource Conversion Efficiency: output share / resource share.
            # 1.0 means the player converted exactly their share of the team's
            # gold into their share of its damage.
            "rce_raw": _safe_div(damage_share, gold_share),
            "rce_z": None,  # filled by the cohort normaliser
        }

    def _vision(self, p: MatchParticipant, minutes: float) -> dict[str, object]:
        return {
            "vision_score_per_min": p.vision_score / minutes,
            "wards_placed_per_min": p.wards_placed / minutes,
            "wards_cleared_per_min": p.wards_killed / minutes,
            "control_wards_per_min": p.detector_wards_placed / minutes,
        }

    def _objectives(self, p: MatchParticipant) -> dict[str, object]:
        """Participation in the team's neutral objectives.

        A player counts as participating if Riot credited them (killer or
        assister) *or* if they were within `OBJECTIVE_PROXIMITY_UNITS` of the pit
        when it fell. The proximity arm matters: the player who held vision on
        the flank while their jungler executed the drake contributed to it, and
        the credit fields alone would score them zero.
        """
        ctx = self.ctx
        pid = p.participant_id
        elites = ctx.events_by_type.get("ELITE_MONSTER_KILL", [])
        if not elites:
            return {
                "objective_participation": None,
                "dragon_participation": None,
                "baron_herald_participation": None,
                "objective_setup_score": None,
                "deaths_before_objectives": 0,
            }

        team_elites = [e for e in elites if self._event_team(e) == p.team_id]

        def rate(subset: list) -> float | None:
            if not subset:
                return None
            hits = sum(1 for e in subset if self._participated(e, pid))
            return hits / len(subset)

        deaths_before = 0
        for e in elites:
            window_start = e.timestamp_ms - 45_000
            deaths_before += sum(
                1 for d in ctx.deaths_of(pid) if window_start <= d.timestamp_ms < e.timestamp_ms
            )

        return {
            "objective_participation": rate(team_elites),
            "dragon_participation": rate(
                [e for e in team_elites if (e.monster_type or "") in ELITE_DRAGONS]
            ),
            "baron_herald_participation": rate(
                [e for e in team_elites if (e.monster_type or "") in ELITE_BARON_HERALD]
            ),
            "objective_setup_score": None,  # filled by the objective analyzer
            "deaths_before_objectives": deaths_before,
        }

    def _event_team(self, event) -> int | None:  # type: ignore[no-untyped-def]
        """Which team took a neutral objective.

        `killerTeamId` is present on modern payloads; when it is not, the killer's
        own team is the answer.
        """
        raw = event.raw if isinstance(event.raw, dict) else {}
        team = raw.get("killerTeamId") or event.team_id
        if team:
            return int(team)
        killer = self.ctx.by_pid.get(event.killer_id) if event.killer_id else None
        return killer.team_id if killer else None

    def _participated(self, event, pid: int) -> bool:  # type: ignore[no-untyped-def]
        if self.ctx.took_part(event, pid):
            return True
        if event.position_x is None:
            return False
        pos = self.ctx.position_at(pid, event.timestamp_ms)
        if pos is None:
            return False
        dx = pos[0] - event.position_x
        dy = pos[1] - (event.position_y or 0.0)
        return (dx * dx + dy * dy) ** 0.5 <= OBJECTIVE_PROXIMITY_UNITS

    def _game_state(
        self, p: MatchParticipant, series: _Series, opp: _Series | None
    ) -> dict[str, object]:
        """Splits performance by whether the player's team was ahead or behind.

        Two averages instead of one: a player who farms well only when winning and
        a player who stabilises from behind have identical season stats and very
        different problems.
        """
        ctx = self.ctx
        diff_15 = ctx.team_gold_diff_at(p.team_id, 15)
        had_lead = diff_15 is not None and diff_15 >= GOLD_STATE_THRESHOLD

        ahead_dmg = behind_dmg = ahead_cs = behind_cs = 0.0
        ahead_min = behind_min = 0
        total_min = 0
        for idx, minute in enumerate(series.minutes):
            if minute == 0:
                continue
            state = ctx.team_gold_diff_at(p.team_id, minute)
            if state is None:
                continue
            total_min += 1
            if state >= GOLD_STATE_THRESHOLD:
                ahead_min += 1
                ahead_dmg += series.damage_delta[idx]
                ahead_cs += series.cs_delta[idx]
            elif state <= -GOLD_STATE_THRESHOLD:
                behind_min += 1
                behind_dmg += series.damage_delta[idx]
                behind_cs += series.cs_delta[idx]

        slope = None
        if opp is not None:
            xs: list[float] = []
            ys: list[float] = []
            for idx, minute in enumerate(series.minutes):
                if 10 <= minute <= 20:
                    theirs = _at_minute(opp, opp.gold, minute)
                    if theirs is not None:
                        xs.append(float(minute))
                        ys.append(series.gold[idx] - theirs)
            slope = _linear_slope(xs, ys)

        return {
            "team_gold_diff_15": diff_15,
            "had_lead_at_15": had_lead,
            "converted_lead": bool(had_lead and p.win),
            "time_ahead_share": (ahead_min / total_min) if total_min else None,
            "dpm_while_ahead": (ahead_dmg / ahead_min) if ahead_min else None,
            "dpm_while_behind": (behind_dmg / behind_min) if behind_min else None,
            "cspm_while_ahead": (ahead_cs / ahead_min) if ahead_min else None,
            "cspm_while_behind": (behind_cs / behind_min) if behind_min else None,
            "gold_diff_slope_10_20": slope,
        }


def compute_and_store_features(session: Session, match_id: str) -> int:
    """(Re)compute `participant_features` for one match. Returns rows written."""
    ctx = MatchContext.load(session, match_id)
    if ctx is None or not ctx.participants:
        return 0

    rows = FeatureBuilder(ctx).build_all()
    existing = {
        f.puuid: f
        for f in session.scalars(
            select(ParticipantFeatures).where(ParticipantFeatures.match_id == match_id)
        )
    }
    for row in rows:
        puuid = str(row["puuid"])
        target = existing.get(puuid)
        if target is None:
            session.add(ParticipantFeatures(**row))
        else:
            for key, value in row.items():
                setattr(target, key, value)

    match = session.get(Match, match_id)
    if match is not None:
        match.features_computed = True
    session.flush()
    return len(rows)


#: Columns the ML layer treats as candidate behavioural features. Kept here so
#: the model and the API agree on one list.
BEHAVIOUR_FEATURES: tuple[str, ...] = (
    "gold_diff_10",
    "gold_diff_15",
    "xp_diff_10",
    "xp_diff_15",
    "cs_diff_10",
    "cs_diff_15",
    "cs_per_min",
    "cs_per_min_first_15",
    "gold_per_min",
    "damage_per_min",
    "kill_participation",
    "early_deaths",
    "deaths_per_10min",
    "solo_kill_diff",
    "damage_per_gold",
    "damage_share",
    "gold_share",
    "rce_raw",
    "vision_score_per_min",
    "wards_placed_per_min",
    "wards_cleared_per_min",
    "control_wards_per_min",
    "objective_participation",
    "dragon_participation",
    "baron_herald_participation",
    "objective_setup_score",
    "deaths_before_objectives",
    "time_ahead_share",
    "dpm_while_ahead",
    "dpm_while_behind",
    "cspm_while_ahead",
    "cspm_while_behind",
    "gold_diff_slope_10_20",
    "roam_count",
    "roam_value_per_roam",
    "roam_cs_sacrificed",
    "roam_success_rate",
    "mean_position_risk",
    "deaths_above_expected",
    "high_risk_exposure_share",
)

#: Human-readable labels used in coaching output and the UI.
FEATURE_LABELS: dict[str, str] = {
    "gold_diff_10": "Gold difference at 10 min",
    "gold_diff_15": "Gold difference at 15 min",
    "xp_diff_10": "XP difference at 10 min",
    "xp_diff_15": "XP difference at 15 min",
    "cs_diff_10": "CS difference at 10 min",
    "cs_diff_15": "CS difference at 15 min",
    "cs_per_min": "CS per minute",
    "cs_per_min_first_15": "CS per minute (first 15)",
    "gold_per_min": "Gold per minute",
    "damage_per_min": "Damage per minute",
    "kill_participation": "Kill participation",
    "early_deaths": "Deaths before 10 min",
    "deaths_per_10min": "Deaths per 10 min",
    "solo_kill_diff": "Solo-kill differential",
    "damage_per_gold": "Damage per gold",
    "damage_share": "Team damage share",
    "gold_share": "Team gold share",
    "rce_raw": "Resource Conversion Efficiency",
    "vision_score_per_min": "Vision score per minute",
    "wards_placed_per_min": "Wards placed per minute",
    "wards_cleared_per_min": "Wards cleared per minute",
    "control_wards_per_min": "Control wards per minute",
    "objective_participation": "Objective participation",
    "dragon_participation": "Dragon participation",
    "baron_herald_participation": "Baron/Herald participation",
    "objective_setup_score": "Objective setup timing",
    "deaths_before_objectives": "Deaths before objectives",
    "time_ahead_share": "Share of game spent ahead",
    "dpm_while_ahead": "Damage per minute while ahead",
    "dpm_while_behind": "Damage per minute while behind",
    "cspm_while_ahead": "CS per minute while ahead",
    "cspm_while_behind": "CS per minute while behind",
    "gold_diff_slope_10_20": "Lane trajectory (10-20 min)",
    "roam_count": "Roams per game",
    "roam_value_per_roam": "Value generated per roam",
    "roam_cs_sacrificed": "CS lost to roaming",
    "roam_success_rate": "Roam success rate",
    "mean_position_risk": "Average positional death risk",
    "deaths_above_expected": "Deaths above positional expectation",
    "high_risk_exposure_share": "Time spent in high-risk map areas",
}

#: Features where a *lower* value is better. Used when phrasing gaps.
LOWER_IS_BETTER: frozenset[str] = frozenset(
    {
        "early_deaths",
        "deaths_per_10min",
        "deaths_before_objectives",
        "roam_cs_sacrificed",
        "mean_position_risk",
        "deaths_above_expected",
        "high_risk_exposure_share",
    }
)

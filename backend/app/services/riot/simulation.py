"""A deterministic Summoner's Rift match simulator.

Why this exists
---------------
A Riot production key is not something a reviewer of this repository will have,
and a personal key is heavily rate limited. Rather than ship an application that
cannot be run, `MockRiotProvider` serves payloads produced by this simulator in
exactly the Match-V5 shape. Ingestion, feature engineering, cohort statistics and
every model run identically against it.

What it is *not*
----------------
This is a data generator, not a model of League of Legends, and nothing learned
from simulated matches says anything about real players. It exists so the
pipeline can be exercised end to end and so tests have realistic fixtures.

It is built around one deliberate property: each simulated player has a latent
skill scalar tied to their rank, and that scalar drives observable behaviour
(CS rate, positioning risk, objective arrival timing, roam success, resource
conversion). That means the Skill Gap model has genuine structure to recover, and
we can assert in tests that it recovers it — a self-check on the methodology
rather than on the game.
"""

from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass, field
from typing import Any

from app.core.constants import (
    BARON_PIT,
    DRAGON_PIT,
    Role,
    Zone,
    tier_rank_score,
)
from app.services.analytics.geometry import (
    classify_zone,
    is_enemy_half,
    lane_point,
)

# --- Static reference data ----------------------------------------------------

#: (championId, name, primary role). Ids and names are the real Data Dragon ones
#: so the frontend can resolve icons; the role affinity is ours.
CHAMPION_POOL: list[tuple[int, str, Role]] = [
    (86, "Garen", Role.TOP),
    (122, "Darius", Role.TOP),
    (24, "Jax", Role.TOP),
    (92, "Riven", Role.TOP),
    (516, "Ornn", Role.TOP),
    (875, "Sett", Role.TOP),
    (64, "LeeSin", Role.JUNGLE),
    (121, "Khazix", Role.JUNGLE),
    (60, "Elise", Role.JUNGLE),
    (254, "Vi", Role.JUNGLE),
    (203, "Kindred", Role.JUNGLE),
    (234, "Viego", Role.JUNGLE),
    (103, "Ahri", Role.MIDDLE),
    (238, "Zed", Role.MIDDLE),
    (134, "Syndra", Role.MIDDLE),
    (245, "Ekko", Role.MIDDLE),
    (157, "Yasuo", Role.MIDDLE),
    (1, "Annie", Role.MIDDLE),
    (222, "Jinx", Role.BOTTOM),
    (145, "Kaisa", Role.BOTTOM),
    (51, "Caitlyn", Role.BOTTOM),
    (236, "Lucian", Role.BOTTOM),
    (22, "Ashe", Role.BOTTOM),
    (498, "Xayah", Role.BOTTOM),
    (412, "Thresh", Role.UTILITY),
    (117, "Lulu", Role.UTILITY),
    (89, "Leona", Role.UTILITY),
    (40, "Janna", Role.UTILITY),
    (111, "Nautilus", Role.UTILITY),
    (12, "Alistar", Role.UTILITY),
]

ROLES: tuple[Role, ...] = (Role.TOP, Role.JUNGLE, Role.MIDDLE, Role.BOTTOM, Role.UTILITY)

#: Baseline per-minute rates by role for a median player (skill = 0.5).
ROLE_CS_PER_MIN: dict[Role, float] = {
    Role.TOP: 6.6,
    Role.JUNGLE: 4.9,
    Role.MIDDLE: 7.1,
    Role.BOTTOM: 7.8,
    Role.UTILITY: 1.2,
}
ROLE_DPM: dict[Role, float] = {
    Role.TOP: 520.0,
    Role.JUNGLE: 480.0,
    Role.MIDDLE: 690.0,
    Role.BOTTOM: 760.0,
    Role.UTILITY: 300.0,
}
ROLE_XPM: dict[Role, float] = {
    Role.TOP: 470.0,
    Role.JUNGLE: 450.0,
    Role.MIDDLE: 500.0,
    Role.BOTTOM: 465.0,
    Role.UTILITY: 340.0,
}
ROLE_WARDS_PER_MIN: dict[Role, float] = {
    Role.TOP: 0.30,
    Role.JUNGLE: 0.55,
    Role.MIDDLE: 0.36,
    Role.BOTTOM: 0.28,
    Role.UTILITY: 1.10,
}
#: Propensity to leave lane, before the skill adjustment.
ROLE_ROAM_RATE: dict[Role, float] = {
    Role.TOP: 0.07,
    Role.JUNGLE: 0.0,  # the jungler is never "roaming"; the whole map is its lane
    Role.MIDDLE: 0.22,
    Role.BOTTOM: 0.05,
    Role.UTILITY: 0.26,
}

#: Cumulative XP needed to reach level n+1 (index 0 -> level 2). Real LoL curve.
_XP_STEPS = [
    280,
    380,
    480,
    580,
    680,
    780,
    880,
    980,
    1080,
    1180,
    1280,
    1380,
    1480,
    1580,
    1680,
    1780,
    1880,
]
XP_THRESHOLDS: list[int] = []
_acc = 0
for _step in _XP_STEPS:
    _acc += _step
    XP_THRESHOLDS.append(_acc)


def level_for_xp(xp: int) -> int:
    level = 1
    for threshold in XP_THRESHOLDS:
        if xp >= threshold:
            level += 1
        else:
            break
    return min(level, 18)


#: How much more likely a death is in each zone, relative to sitting in own lane.
#: This is the structure the spatial risk model is meant to rediscover from data.
ZONE_DEATH_MULTIPLIER: dict[Zone, float] = {
    Zone.BLUE_BASE: 0.02,
    Zone.RED_BASE: 0.02,
    Zone.TOP_LANE: 1.0,
    Zone.MID_LANE: 1.0,
    Zone.BOT_LANE: 1.0,
    Zone.TOP_RIVER: 1.75,
    Zone.BOT_RIVER: 1.75,
    Zone.DRAGON_PIT: 2.10,
    Zone.BARON_PIT: 2.25,
    Zone.BLUE_TOP_JUNGLE: 1.35,
    Zone.BLUE_BOT_JUNGLE: 1.35,
    Zone.RED_TOP_JUNGLE: 1.35,
    Zone.RED_BOT_JUNGLE: 1.35,
}

PHASE_DEATH_BASE: tuple[float, float, float] = (0.042, 0.082, 0.100)


def stable_seed(*parts: object) -> int:
    """Deterministic 63-bit seed from arbitrary parts (stable across runs/hosts)."""
    digest = hashlib.sha256("|".join(str(p) for p in parts).encode()).digest()
    return int.from_bytes(digest[:8], "big") & ((1 << 63) - 1)


# --- Player description -------------------------------------------------------


@dataclass(slots=True)
class SimPlayer:
    puuid: str
    game_name: str
    tag_line: str
    participant_id: int
    team_id: int
    role: Role
    champion_id: int
    champion_name: str
    #: Latent skill in [0, 1]; the generative cause of everything observable.
    skill: float
    tier: str
    division: str | None
    league_points: int

    #: Per-game form multiplier around the player's latent skill. Real players
    #: are not the same player every game, and without this the within-band
    #: spread is unrealistically tight — every cohort percentile would be
    #: extreme for anyone even slightly off their band's centre.
    form: float = 1.0

    # accumulated during simulation
    cs: float = 0.0
    jungle_cs: float = 0.0
    gold: float = 500.0
    xp: float = 0.0
    damage: float = 0.0
    damage_taken: float = 0.0
    kills: int = 0
    deaths: int = 0
    assists: int = 0
    wards_placed: int = 0
    wards_killed: int = 0
    control_wards: int = 0
    dragon_takedowns: int = 0
    baron_takedowns: int = 0
    turret_takedowns: int = 0
    time_dead: float = 0.0
    #: seconds remaining on the death timer, if dead
    respawn_at: float = -1.0
    position: tuple[float, float] = (0.0, 0.0)
    frames: list[dict[str, Any]] = field(default_factory=list)

    @property
    def total_cs(self) -> int:
        return int(self.cs + self.jungle_cs)


@dataclass(slots=True)
class SimulatedMatch:
    match: dict[str, Any]
    timeline: dict[str, Any]


# --- The simulator ------------------------------------------------------------


class MatchSimulator:
    """Produces one Match-V5 match + timeline pair from a roster of players."""

    FRAME_INTERVAL_MS = 60_000

    def __init__(
        self,
        match_id: str,
        platform: str,
        players: list[SimPlayer],
        *,
        patch: str = "14.19",
        queue_id: int = 420,
        game_start_ms: int | None = None,
        seed: int | None = None,
    ) -> None:
        if len(players) != 10:
            raise ValueError("a simulated match needs exactly 10 players")
        self.match_id = match_id
        self.platform = platform
        self.players = players
        self.patch = patch
        self.queue_id = queue_id
        self.rng = random.Random(seed if seed is not None else stable_seed(match_id))
        self.game_start_ms = game_start_ms or 1_700_000_000_000
        self.events: list[dict[str, Any]] = []
        self.by_pid: dict[int, SimPlayer] = {p.participant_id: p for p in players}
        self.team_kills: dict[int, int] = {100: 0, 200: 0}
        self.team_objectives: dict[int, dict[str, int]] = {
            100: {"dragon": 0, "baron": 0, "herald": 0, "tower": 0, "inhibitor": 0},
            200: {"dragon": 0, "baron": 0, "herald": 0, "tower": 0, "inhibitor": 0},
        }
        self.first_flags: dict[str, int | None] = {
            "blood": None,
            "tower": None,
            "dragon": None,
            "baron": None,
        }
        self.duration_seconds = 0
        self.winning_team = 100
        #: minute -> set of participant ids currently roaming (used for CS penalty)
        self._roaming: dict[int, set[int]] = {}

    # --- helpers ---------------------------------------------------------

    def team(self, team_id: int) -> list[SimPlayer]:
        return [p for p in self.players if p.team_id == team_id]

    def enemies_of(self, player: SimPlayer) -> list[SimPlayer]:
        return [p for p in self.players if p.team_id != player.team_id]

    def team_skill(self, team_id: int) -> float:
        members = self.team(team_id)
        return sum(p.skill for p in members) / len(members)

    def team_gold(self, team_id: int) -> float:
        return sum(p.gold for p in self.team(team_id))

    def _jitter(self, point: tuple[float, float], sigma: float) -> tuple[float, float]:
        return (
            point[0] + self.rng.gauss(0, sigma),
            point[1] + self.rng.gauss(0, sigma),
        )

    # --- schedule --------------------------------------------------------

    def _pick_duration(self) -> int:
        """Game length in seconds; skewed like real solo-queue distributions."""
        minutes = min(48.0, max(17.0, self.rng.gauss(30.0, 5.5)))
        return int(minutes * 60)

    def _objective_schedule(self) -> list[tuple[int, str, str | None]]:
        """(timestamp_seconds, objective_type, sub_type) for the whole game."""
        schedule: list[tuple[int, str, str | None]] = []
        # Rift Herald spawns in the early game and is usually taken twice.
        for t in (int(self.rng.uniform(9, 11) * 60), int(self.rng.uniform(14, 16) * 60)):
            if t < self.duration_seconds:
                schedule.append((t, "RIFTHERALD", None))
        # Dragons on a roughly five minute cadence from ~5:00.
        drake_types = ["FIRE_DRAGON", "WATER_DRAGON", "AIR_DRAGON", "EARTH_DRAGON"]
        t = int(self.rng.uniform(4.7, 5.6) * 60)
        while t < self.duration_seconds:
            schedule.append((t, "DRAGON", self.rng.choice(drake_types)))
            t += int(self.rng.uniform(4.8, 6.4) * 60)
        # Baron from 20:00 onwards.
        t = int(self.rng.uniform(20.0, 23.0) * 60)
        while t < self.duration_seconds:
            schedule.append((t, "BARON_NASHOR", None))
            t += int(self.rng.uniform(6.0, 8.0) * 60)
        schedule.sort()
        return schedule

    # --- positioning -----------------------------------------------------

    def _position_for(
        self,
        player: SimPlayer,
        minute: int,
        objective_ctx: tuple[int, str, str | None] | None,
    ) -> tuple[float, float]:
        """Where this player is standing at the start of `minute`.

        The ordering encodes intent: dead players sit in base, objective setup
        beats roaming, roaming beats standing in lane.
        """
        if player.respawn_at > minute * 60:
            base = (1200.0, 1200.0) if player.team_id == 100 else (13800.0, 13800.0)
            return self._jitter(base, 350)

        if objective_ctx is not None:
            obj_time, obj_type, _ = objective_ctx
            pit = DRAGON_PIT if obj_type == "DRAGON" else BARON_PIT
            seconds_out = obj_time - minute * 60
            # Better players are already in position a minute out; weaker ones
            # arrive late or not at all. This is the objective-setup signal.
            arrival_slack = 90.0 * (1.0 - player.skill) + self.rng.uniform(0, 45)
            if seconds_out <= arrival_slack:
                return self._jitter(pit, 700)

        if player.participant_id in self._roaming.get(minute, set()):
            target = self._roam_target(player)
            return self._jitter(target, 600)

        if player.role is Role.JUNGLE:
            return self._jitter(self._jungle_position(player, minute), 900)

        # Lane. Push state drifts with the player's own advantage.
        progress_own_side = 0.42 if player.team_id == 100 else 0.58
        push = 0.06 * math.tanh((player.skill - 0.5) * 3.0)
        progress = progress_own_side + (push if player.team_id == 100 else -push)
        progress += self.rng.gauss(0, 0.05)
        return self._jitter(lane_point(player.role, max(0.05, min(0.95, progress))), 450)

    def _jungle_position(self, player: SimPlayer, minute: int) -> tuple[float, float]:
        """Junglers path between quadrants; stronger ones invade more."""
        invade = self.rng.random() < (0.18 + 0.30 * player.skill)
        blue_side = player.team_id == 100
        own_half = not invade if blue_side else invade
        top_half = self.rng.random() < 0.5
        # Quadrant centres, chosen to sit clearly inside the jungle zones.
        if own_half:
            base = (3800.0, 8200.0) if top_half else (8200.0, 3800.0)
        else:
            base = (6800.0, 11200.0) if top_half else (11200.0, 6800.0)
        if not blue_side:
            # Mirror across the map diagonal for the red-side jungler.
            base = (15000.0 - base[0], 15000.0 - base[1])
        return base

    def _roam_target(self, player: SimPlayer) -> tuple[float, float]:
        """Where a roaming laner goes: a different lane, or the river."""
        if self.rng.random() < 0.45:
            return DRAGON_PIT if self.rng.random() < 0.5 else BARON_PIT
        other = [r for r in (Role.TOP, Role.MIDDLE, Role.BOTTOM) if r is not player.role]
        target_role = self.rng.choice(other)
        progress = 0.45 if player.team_id == 100 else 0.55
        return lane_point(target_role, progress)

    # --- main loop -------------------------------------------------------

    def simulate(self) -> SimulatedMatch:
        self.duration_seconds = self._pick_duration()
        schedule = self._objective_schedule()
        total_minutes = self.duration_seconds // 60

        for p in self.players:
            p.position = self._position_for(p, 0, None)

        frames: list[dict[str, Any]] = [self._build_frame(0)]

        for minute in range(1, total_minutes + 1):
            now_s = minute * 60
            self._plan_roams(minute)
            upcoming = self._objective_in_window(schedule, now_s)

            for p in self.players:
                p.position = self._position_for(p, minute, upcoming)

            self._accrue_economy(minute)
            self._simulate_wards(minute)
            self._simulate_deaths(minute)
            self._resolve_objectives(schedule, minute)
            self._simulate_towers(minute)

            frames.append(self._build_frame(now_s))

        self._decide_winner()
        self._emit_game_end()
        return SimulatedMatch(match=self._build_match(), timeline=self._build_timeline(frames))

    def _objective_in_window(
        self, schedule: list[tuple[int, str, str | None]], now_s: int
    ) -> tuple[int, str, str | None] | None:
        """The next contested objective within the following 100 seconds."""
        for entry in schedule:
            if now_s <= entry[0] <= now_s + 100:
                return entry
        return None

    def _plan_roams(self, minute: int) -> None:
        """Decide who leaves lane this minute.

        Skill raises both the rate and (later) the success of roams, but roaming
        always costs lane CS — which is exactly the trade-off the roam-value
        metric is meant to measure.
        """
        roamers: set[int] = set()
        if 5 <= minute <= max(6, int(self.duration_seconds / 60) - 5):
            for p in self.players:
                rate = ROLE_ROAM_RATE[p.role] * (0.55 + 0.9 * p.skill)
                if p.respawn_at <= minute * 60 and self.rng.random() < rate:
                    roamers.add(p.participant_id)
        self._roaming[minute] = roamers

    def _accrue_economy(self, minute: int) -> None:
        roamers = self._roaming.get(minute, set())
        for p in self.players:
            if p.respawn_at > minute * 60:
                continue  # dead: no farm this minute
            skill_mult = (0.62 + 0.76 * p.skill) * p.form
            cs_rate = ROLE_CS_PER_MIN[p.role] * skill_mult
            if p.participant_id in roamers:
                # Time spent out of lane is CS not taken. Better players lose less
                # (crashing the wave first), which the roam model can recover.
                cs_rate *= 0.25 + 0.35 * p.skill
            cs_gain = max(0.0, self.rng.gauss(cs_rate, cs_rate * 0.18))
            if p.role is Role.JUNGLE:
                p.jungle_cs += cs_gain
            else:
                p.cs += cs_gain

            gold_per_cs = 30.0 if p.role is Role.JUNGLE else 21.0
            p.gold += 122.0 + cs_gain * gold_per_cs
            p.xp += max(
                0.0, self.rng.gauss(ROLE_XPM[p.role] * (0.72 + 0.55 * p.skill) * p.form, 45)
            )

            dmg = ROLE_DPM[p.role] * (0.55 + 0.9 * p.skill) * p.form
            phase_scale = 0.55 if minute < 14 else (1.0 if minute < 25 else 1.25)
            p.damage += max(0.0, self.rng.gauss(dmg * phase_scale, dmg * 0.25))
            p.damage_taken += max(0.0, self.rng.gauss(dmg * phase_scale * 0.9, dmg * 0.3))

    def _simulate_wards(self, minute: int) -> None:
        for p in self.players:
            if p.respawn_at > minute * 60:
                continue
            rate = ROLE_WARDS_PER_MIN[p.role] * (0.45 + 1.1 * p.skill) * p.form
            n = self._poisson(rate)
            for _ in range(n):
                ts = minute * 60_000 + self.rng.randrange(0, 60_000)
                is_control = self.rng.random() < 0.22 + 0.18 * p.skill
                p.wards_placed += 1
                if is_control:
                    p.control_wards += 1
                self.events.append(
                    {
                        "type": "WARD_PLACED",
                        "timestamp": ts,
                        "creatorId": p.participant_id,
                        "wardType": "CONTROL_WARD" if is_control else "YELLOW_TRINKET",
                    }
                )
            # Clearing enemy vision scales with skill more steeply than placing.
            if self.rng.random() < 0.05 + 0.20 * p.skill:
                p.wards_killed += 1
                self.events.append(
                    {
                        "type": "WARD_KILL",
                        "timestamp": minute * 60_000 + self.rng.randrange(0, 60_000),
                        "killerId": p.participant_id,
                        "wardType": "YELLOW_TRINKET",
                    }
                )

    def _simulate_deaths(self, minute: int) -> None:
        phase_idx = 0 if minute < 14 else (1 if minute < 25 else 2)
        base = PHASE_DEATH_BASE[phase_idx]
        for p in self.players:
            if p.respawn_at > minute * 60:
                continue
            x, y = p.position
            zone = classify_zone(x, y)
            zone_mult = ZONE_DEATH_MULTIPLIER.get(zone, 1.0)
            if is_enemy_half(x, y, p.team_id) and zone in {
                Zone.TOP_LANE,
                Zone.MID_LANE,
                Zone.BOT_LANE,
            }:
                zone_mult *= 1.25
            # Off-form games are also sloppier games.
            skill_mult = (1.40 - 0.80 * p.skill) / max(p.form, 0.5)
            risk = base * zone_mult * skill_mult
            if p.participant_id in self._roaming.get(minute, set()):
                risk *= 1.15
            if self.rng.random() < min(risk, 0.85):
                self._kill_player(p, minute)

    def _kill_player(self, victim: SimPlayer, minute: int) -> None:
        ts = minute * 60_000 + self.rng.randrange(0, 60_000)
        enemies = [e for e in self.enemies_of(victim) if e.respawn_at <= minute * 60]
        if not enemies:
            return
        weights = [0.4 + e.skill for e in enemies]
        killer = self.rng.choices(enemies, weights=weights)[0]

        # A stronger killer is likelier to have done it alone; the "solo kill"
        # signal is generated here rather than being an artefact of assist counts.
        solo_p = 0.18 + 0.45 * killer.skill
        if self.rng.random() < solo_p:
            assisters: list[SimPlayer] = []
        else:
            pool = [e for e in enemies if e is not killer]
            k = min(len(pool), self.rng.choice([1, 1, 2, 2, 3]))
            assisters = self.rng.sample(pool, k) if k else []

        victim.deaths += 1
        killer.kills += 1
        for a in assisters:
            a.assists += 1
        self.team_kills[killer.team_id] += 1
        if self.first_flags["blood"] is None:
            self.first_flags["blood"] = killer.participant_id

        death_timer = 8.0 + 2.2 * minute * 0.35
        victim.respawn_at = ts / 1000.0 + death_timer
        victim.time_dead += death_timer

        gold = 300 if not assisters else 240
        killer.gold += gold
        for a in assisters:
            a.gold += 140
        killer.xp += 120

        x, y = self._jitter(victim.position, 250)
        self.events.append(
            {
                "type": "CHAMPION_KILL",
                "timestamp": ts,
                "killerId": killer.participant_id,
                "victimId": victim.participant_id,
                "assistingParticipantIds": [a.participant_id for a in assisters],
                "position": {"x": round(x), "y": round(y)},
                "bounty": gold,
                "shutdownBounty": 0,
            }
        )
        if not assisters:
            self.events.append(
                {
                    "type": "CHAMPION_SPECIAL_KILL",
                    "timestamp": ts,
                    "killerId": killer.participant_id,
                    "killType": "KILL_FIRST_BLOOD"
                    if self.first_flags["blood"] == killer.participant_id
                    and self.team_kills[killer.team_id] == 1
                    else "KILL_SOLO",
                    "position": {"x": round(x), "y": round(y)},
                }
            )

    def _resolve_objectives(self, schedule: list[tuple[int, str, str | None]], minute: int) -> None:
        window_start, window_end = (minute - 1) * 60, minute * 60
        for obj_time, obj_type, sub_type in schedule:
            if not (window_start < obj_time <= window_end):
                continue
            # Who takes it: team strength plus a real dose of variance.
            edge = (self.team_skill(100) - self.team_skill(200)) * 2.4
            gold_edge = (self.team_gold(100) - self.team_gold(200)) / 12000.0
            p_blue = 1.0 / (1.0 + math.exp(-(edge + gold_edge)))
            team_id = 100 if self.rng.random() < p_blue else 200
            takers = [p for p in self.team(team_id) if p.respawn_at <= obj_time]
            if not takers:
                continue
            killer = max(takers, key=lambda p: p.skill + self.rng.random() * 0.6)
            # Presence is skill-weighted, which is what the participation and
            # setup metrics are meant to pick up.
            assisters = [
                p for p in takers if p is not killer and self.rng.random() < 0.35 + 0.55 * p.skill
            ]

            pit = DRAGON_PIT if obj_type == "DRAGON" else BARON_PIT
            x, y = self._jitter(pit, 200)
            self.events.append(
                {
                    "type": "ELITE_MONSTER_KILL",
                    "timestamp": obj_time * 1000,
                    "killerId": killer.participant_id,
                    "assistingParticipantIds": [a.participant_id for a in assisters],
                    "killerTeamId": team_id,
                    "monsterType": obj_type,
                    **({"monsterSubType": sub_type} if sub_type else {}),
                    "position": {"x": round(x), "y": round(y)},
                }
            )
            key = {"DRAGON": "dragon", "BARON_NASHOR": "baron", "RIFTHERALD": "herald"}[obj_type]
            self.team_objectives[team_id][key] += 1
            if key == "dragon":
                for p in [killer, *assisters]:
                    p.dragon_takedowns += 1
                if self.first_flags["dragon"] is None:
                    self.first_flags["dragon"] = team_id
            elif key == "baron":
                for p in [killer, *assisters]:
                    p.baron_takedowns += 1
                if self.first_flags["baron"] is None:
                    self.first_flags["baron"] = team_id
            reward = 300 if key != "baron" else 600
            for p in [killer, *assisters]:
                p.gold += reward

    def _simulate_towers(self, minute: int) -> None:
        if minute < 8:
            return
        diff = self.team_gold(100) - self.team_gold(200)
        for team_id in (100, 200):
            signed = diff if team_id == 100 else -diff
            p_tower = 0.10 + max(0.0, signed) / 26000.0
            if self.rng.random() >= min(p_tower, 0.45):
                continue
            takers = [p for p in self.team(team_id) if p.respawn_at <= minute * 60]
            if not takers:
                continue
            taker = self.rng.choice(takers)
            taker.turret_takedowns += 1
            self.team_objectives[team_id]["tower"] += 1
            if self.first_flags["tower"] is None:
                self.first_flags["tower"] = team_id
            lane = self.rng.choice(["TOP_LANE", "MID_LANE", "BOT_LANE"])
            enemy_progress = 0.85 if team_id == 100 else 0.15
            role = {"TOP_LANE": Role.TOP, "MID_LANE": Role.MIDDLE, "BOT_LANE": Role.BOTTOM}[lane]
            x, y = lane_point(role, enemy_progress)
            for p in takers:
                p.gold += 110
            self.events.append(
                {
                    "type": "BUILDING_KILL",
                    "timestamp": minute * 60_000 + self.rng.randrange(0, 60_000),
                    "killerId": taker.participant_id,
                    "assistingParticipantIds": [],
                    "teamId": 200 if team_id == 100 else 100,
                    "buildingType": "TOWER_BUILDING",
                    "towerType": self.rng.choice(["OUTER_TURRET", "INNER_TURRET", "BASE_TURRET"]),
                    "laneType": lane,
                    "position": {"x": round(x), "y": round(y)},
                }
            )

    def _decide_winner(self) -> None:
        gold_diff = self.team_gold(100) - self.team_gold(200)
        obj_diff = (
            self.team_objectives[100]["tower"] - self.team_objectives[200]["tower"]
        ) * 400 + (self.team_objectives[100]["baron"] - self.team_objectives[200]["baron"]) * 900
        score = (gold_diff + obj_diff) / 6000.0
        p_blue = 1.0 / (1.0 + math.exp(-score))
        self.winning_team = 100 if self.rng.random() < p_blue else 200
        loser = 200 if self.winning_team == 100 else 100
        self.team_objectives[self.winning_team]["inhibitor"] += self.rng.choice([1, 1, 2])
        self.team_objectives[self.winning_team]["tower"] = max(
            self.team_objectives[self.winning_team]["tower"], 5
        )
        self.team_objectives[loser]["tower"] = min(self.team_objectives[loser]["tower"], 9)

    def _emit_game_end(self) -> None:
        self.events.append(
            {
                "type": "GAME_END",
                "timestamp": self.duration_seconds * 1000,
                "winningTeam": self.winning_team,
                "gameId": stable_seed(self.match_id) % 10_000_000,
            }
        )

    def _poisson(self, lam: float) -> int:
        """Knuth's algorithm; `lam` here is always small (< 3)."""
        if lam <= 0:
            return 0
        target = math.exp(-lam)
        k, prod = 0, 1.0
        while True:
            prod *= self.rng.random()
            if prod <= target:
                return k
            k += 1
            if k > 20:
                return k

    # --- payload assembly -------------------------------------------------

    def _build_frame(self, timestamp_s: int) -> dict[str, Any]:
        participant_frames: dict[str, Any] = {}
        for p in self.players:
            x, y = p.position
            participant_frames[str(p.participant_id)] = {
                "participantId": p.participant_id,
                "currentGold": int(p.gold * 0.18),
                "totalGold": int(p.gold),
                "level": level_for_xp(int(p.xp)),
                "xp": int(p.xp),
                "minionsKilled": int(p.cs),
                "jungleMinionsKilled": int(p.jungle_cs),
                "timeEnemySpentControlled": 0,
                "position": {"x": round(x), "y": round(y)},
                "damageStats": {
                    "totalDamageDoneToChampions": int(p.damage),
                    "totalDamageTaken": int(p.damage_taken),
                },
            }
        frame_events = [
            e
            for e in self.events
            if timestamp_s * 1000 - self.FRAME_INTERVAL_MS < e["timestamp"] <= timestamp_s * 1000
        ]
        return {
            "timestamp": timestamp_s * 1000,
            "participantFrames": participant_frames,
            "events": frame_events,
        }

    def _build_timeline(self, frames: list[dict[str, Any]]) -> dict[str, Any]:
        # Events in the final partial minute fall after the last frame boundary
        # and would otherwise be dropped. Carry them in a closing frame — unless
        # the game ended exactly on a frame boundary, in which case that frame
        # already exists and the events are merged into it rather than creating a
        # duplicate at the same timestamp.
        last_ts = frames[-1]["timestamp"] if frames else 0
        tail = [e for e in self.events if e["timestamp"] > last_ts]
        if tail:
            end_ts = self.duration_seconds * 1000
            if end_ts > last_ts:
                frames.append(
                    {
                        "timestamp": end_ts,
                        "participantFrames": frames[-1]["participantFrames"],
                        "events": tail,
                    }
                )
            else:
                frames[-1]["events"] = [*frames[-1]["events"], *tail]
        return {
            "metadata": {
                "dataVersion": "2",
                "matchId": self.match_id,
                "participants": [p.puuid for p in self.players],
            },
            "info": {
                "frameInterval": self.FRAME_INTERVAL_MS,
                "gameId": stable_seed(self.match_id) % 10_000_000,
                "participants": [
                    {"participantId": p.participant_id, "puuid": p.puuid} for p in self.players
                ],
                "frames": frames,
            },
        }

    def _build_match(self) -> dict[str, Any]:
        participants = []
        for p in self.players:
            won = p.team_id == self.winning_team
            participants.append(
                {
                    "puuid": p.puuid,
                    "participantId": p.participant_id,
                    "teamId": p.team_id,
                    "win": won,
                    "riotIdGameName": p.game_name,
                    "riotIdTagline": p.tag_line,
                    "championId": p.champion_id,
                    "championName": p.champion_name,
                    "champLevel": level_for_xp(int(p.xp)),
                    "teamPosition": p.role.value,
                    "individualPosition": p.role.value,
                    "lane": {"UTILITY": "BOTTOM"}.get(p.role.value, p.role.value),
                    "kills": p.kills,
                    "deaths": p.deaths,
                    "assists": p.assists,
                    "goldEarned": int(p.gold),
                    "goldSpent": int(p.gold * 0.88),
                    "totalMinionsKilled": int(p.cs),
                    "neutralMinionsKilled": int(p.jungle_cs),
                    "totalDamageDealtToChampions": int(p.damage),
                    "physicalDamageDealtToChampions": int(p.damage * 0.55),
                    "magicDamageDealtToChampions": int(p.damage * 0.38),
                    "trueDamageDealtToChampions": int(p.damage * 0.07),
                    "totalDamageTaken": int(p.damage_taken),
                    "damageSelfMitigated": int(p.damage_taken * 0.6),
                    "totalHealsOnTeammates": int(p.damage * 0.05) if p.role is Role.UTILITY else 0,
                    "damageDealtToObjectives": int(p.damage * 0.4),
                    "damageDealtToTurrets": int(p.damage * 0.22),
                    "visionScore": int(
                        p.wards_placed * 1.05 + p.wards_killed * 1.15 + p.control_wards * 1.4
                    ),
                    "wardsPlaced": p.wards_placed,
                    "wardsKilled": p.wards_killed,
                    "detectorWardsPlaced": p.control_wards,
                    "visionWardsBoughtInGame": p.control_wards,
                    "turretTakedowns": p.turret_takedowns,
                    "dragonKills": p.dragon_takedowns,
                    "baronKills": p.baron_takedowns,
                    "objectivesStolen": 0,
                    "timeCCingOthers": int(p.damage * 0.02),
                    "totalTimeSpentDead": int(p.time_dead),
                    "longestTimeSpentLiving": int(self.duration_seconds * (0.25 + 0.4 * p.skill)),
                    "firstBloodKill": self.first_flags["blood"] == p.participant_id,
                    "firstTowerKill": False,
                    "summoner1Id": 4,
                    "summoner2Id": 12 if p.role is Role.TOP else 14,
                    "item0": 0,
                    "item1": 0,
                    "item2": 0,
                    "item3": 0,
                    "item4": 0,
                    "item5": 0,
                    "item6": 3340,
                    "perks": {},
                }
            )

        teams: list[dict[str, Any]] = []
        for team_id in (100, 200):
            o = self.team_objectives[team_id]
            teams.append(
                {
                    "teamId": team_id,
                    "win": team_id == self.winning_team,
                    "bans": [],
                    "objectives": {
                        "baron": {
                            "first": self.first_flags["baron"] == team_id,
                            "kills": o["baron"],
                        },
                        "champion": {
                            "first": bool(
                                self.first_flags["blood"]
                                and self.by_pid[self.first_flags["blood"]].team_id == team_id
                            ),
                            "kills": self.team_kills[team_id],
                        },
                        "dragon": {
                            "first": self.first_flags["dragon"] == team_id,
                            "kills": o["dragon"],
                        },
                        "inhibitor": {"first": False, "kills": o["inhibitor"]},
                        "riftHerald": {"first": False, "kills": o["herald"]},
                        "tower": {
                            "first": self.first_flags["tower"] == team_id,
                            "kills": o["tower"],
                        },
                    },
                }
            )

        return {
            "metadata": {
                "dataVersion": "2",
                "matchId": self.match_id,
                "participants": [p.puuid for p in self.players],
            },
            "info": {
                "gameId": stable_seed(self.match_id) % 10_000_000,
                "gameCreation": self.game_start_ms - 90_000,
                "gameStartTimestamp": self.game_start_ms,
                "gameEndTimestamp": self.game_start_ms + self.duration_seconds * 1000,
                "gameDuration": self.duration_seconds,
                "gameMode": "CLASSIC",
                "gameType": "MATCHED_GAME",
                "gameVersion": f"{self.patch}.500.1234",
                "mapId": 11,
                "platformId": self.platform.upper(),
                "queueId": self.queue_id,
                "participants": participants,
                "teams": teams,
            },
        }


def rank_for_skill(skill: float) -> tuple[str, str | None, int]:
    """Invert the latent-skill scale into a plausible tier/division/LP."""
    bands: list[tuple[float, str]] = [
        (0.12, "IRON"),
        (0.22, "BRONZE"),
        (0.35, "SILVER"),
        (0.48, "GOLD"),
        (0.60, "PLATINUM"),
        (0.71, "EMERALD"),
        (0.82, "DIAMOND"),
        (0.90, "MASTER"),
        (0.96, "GRANDMASTER"),
        (1.01, "CHALLENGER"),
    ]
    tier = next(name for edge, name in bands if skill < edge)
    if tier in {"MASTER", "GRANDMASTER", "CHALLENGER"}:
        return tier, None, int((skill - 0.82) * 1500)
    # Within a tier, higher skill maps to a better division.
    idx = int(((skill * 100) % 12) / 3)
    division = ["IV", "III", "II", "I"][min(idx, 3)]
    return tier, division, int((skill * 1000) % 100)


#: Prefix marking a synthetic PUUID that carries its own latent skill.
SIM_SKILL_PREFIX = "simx"


def encode_sim_puuid(skill: float, *salt: object) -> str:
    """Build a synthetic PUUID that encodes the player's latent skill.

    The simulator assigns a peer their skill *before* they have an identity, but
    the provider is later asked for that same account's rank by PUUID alone. If
    the two were derived independently the persisted rank would not match the
    behaviour in the game, and every rank-based analysis downstream would be
    fitting noise. Carrying the skill in the identifier keeps the simulated world
    self-consistent, and costs nothing since these ids are not real PUUIDs.
    """
    bucket = min(9999, max(0, round(skill * 10000)))
    return f"{SIM_SKILL_PREFIX}{bucket:04d}{stable_seed(*salt):015d}"


def skill_for_puuid(puuid: str) -> float:
    """Latent skill for a synthetic account.

    Decoded from the identifier when it carries one (see `encode_sim_puuid`);
    otherwise drawn deterministically from a Beta distribution shaped like a real
    ranked ladder — most players in the middle, thin tails at either end.
    """
    if puuid.startswith(SIM_SKILL_PREFIX):
        digits = puuid[len(SIM_SKILL_PREFIX) : len(SIM_SKILL_PREFIX) + 4]
        if digits.isdigit():
            return min(0.985, max(0.02, int(digits) / 10000.0))
    rng = random.Random(stable_seed("skill", puuid))
    return min(0.985, max(0.05, rng.betavariate(4.2, 4.0)))


def build_roster(
    focus_puuid: str,
    focus_name: str,
    focus_tag: str,
    *,
    seed: int,
    focus_skill: float | None = None,
) -> list[SimPlayer]:
    """Assemble ten players around a focus account, matched on skill.

    Matchmaking is modelled as sampling the other nine from a tight band around
    the focus player's rating, which is what makes cohort comparison meaningful:
    the peers in a game really are peers.
    """
    rng = random.Random(seed)
    focus = focus_skill if focus_skill is not None else skill_for_puuid(focus_puuid)
    focus_role = rng.choice(ROLES)
    focus_team = rng.choice([100, 200])

    players: list[SimPlayer] = []
    slots = [(team, role) for team in (100, 200) for role in ROLES]
    used_champions: set[int] = set()

    for idx, (team_id, role) in enumerate(slots, start=1):
        is_focus = team_id == focus_team and role is focus_role
        if is_focus:
            puuid, name, tag = focus_puuid, focus_name, focus_tag
            skill = focus
        else:
            skill = min(0.985, max(0.02, rng.gauss(focus, 0.045)))
            name = f"Peer{idx}{rng.randrange(100, 999)}"
            tag = rng.choice(["NA1", "EUW", "KR1", "LAN"])
            # The identifier carries the skill so that this player's rank, when
            # the provider is later asked for it, matches how they just played.
            puuid = encode_sim_puuid(skill, seed, idx, name)
        pool = [c for c in CHAMPION_POOL if c[2] is role and c[0] not in used_champions]
        champ_id, champ_name, _ = rng.choice(pool or [c for c in CHAMPION_POOL if c[2] is role])
        used_champions.add(champ_id)
        tier, division, lp = rank_for_skill(skill)
        players.append(
            SimPlayer(
                form=min(1.45, max(0.6, rng.gauss(1.0, 0.13))),
                puuid=puuid,
                game_name=name,
                tag_line=tag,
                participant_id=idx,
                team_id=team_id,
                role=role,
                champion_id=champ_id,
                champion_name=champ_name,
                skill=skill,
                tier=tier,
                division=division,
                league_points=lp,
            )
        )
    return players


def rank_score_for_player(p: SimPlayer) -> float:
    return tier_rank_score(p.tier, p.division, p.league_points)

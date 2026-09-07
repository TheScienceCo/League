"""A `RiotProvider` backed by the local match simulator.

Selected automatically when no `RIOT_API_KEY` is configured (or when
`RIOT_USE_MOCK=true`), so the application is always runnable. Responses are
deterministic for a given PUUID + seed, which makes tests and demos reproducible.
"""

from __future__ import annotations

import random
from functools import lru_cache

from app.core.errors import NotFoundError
from app.services.riot.dto import (
    AccountDTO,
    LeagueEntryDTO,
    MatchDTO,
    SummonerDTO,
    TimelineDTO,
)
from app.services.riot.simulation import (
    MatchSimulator,
    SimPlayer,
    build_roster,
    rank_for_skill,
    skill_for_puuid,
    stable_seed,
)

#: Demo accounts that always resolve to a known skill level, used by the seed
#: script and the UI's example links. Any *other* Riot ID also resolves — to a
#: deterministic synthetic player derived from the hash of its name.
DEMO_ACCOUNTS: dict[str, float] = {
    "RiftLabDemo#NA1": 0.55,
    "ChallengerSmurf#KR1": 0.94,
    "GoldPlateau#EUW": 0.45,
    "IronWill#NA1": 0.14,
}


def mock_puuid_for(game_name: str, tag_line: str) -> str:
    """Stable synthetic PUUID for a Riot ID."""
    return f"sim-{stable_seed('account', game_name.lower(), tag_line.lower()):019d}"[:40]


@lru_cache(maxsize=2048)
def _match_count_for(puuid: str) -> int:
    return random.Random(stable_seed("count", puuid)).randint(40, 90)


class MockRiotProvider:
    """Implements `RiotProvider` from simulated data.

    A simulated match is a pure function of `(match_id, focus_puuid)`. To keep a
    given match id resolving to the *same* game regardless of who asks for it, the
    provider remembers which account each id was issued for. Ids that were never
    issued (a hand-typed URL, say) fall back to an anchor account derived from the
    id itself, so the provider never 404s on a well-formed id.
    """

    def __init__(
        self,
        *,
        seed: int = 1337,
        patch_pool: tuple[str, ...] = ("14.18", "14.19", "14.20"),
    ) -> None:
        self.seed = seed
        self.patch_pool = patch_pool
        self._name_by_puuid: dict[str, tuple[str, str]] = {}
        self._demo_skill: dict[str, float] = {}
        self._match_owner: dict[str, str] = {}
        for riot_id, skill in DEMO_ACCOUNTS.items():
            name, tag = riot_id.split("#")
            puuid = mock_puuid_for(name, tag)
            self._name_by_puuid[puuid] = (name, tag)
            self._demo_skill[puuid] = skill

    # --- identity ---------------------------------------------------------

    async def get_account_by_riot_id(
        self, game_name: str, tag_line: str, *, platform: str
    ) -> AccountDTO:
        if not game_name or not tag_line:
            raise NotFoundError("a Riot ID needs both a name and a tag line")
        puuid = mock_puuid_for(game_name, tag_line)
        self._name_by_puuid[puuid] = (game_name, tag_line)
        return AccountDTO(puuid=puuid, gameName=game_name, tagLine=tag_line)

    async def get_account_by_puuid(self, puuid: str, *, platform: str) -> AccountDTO:
        name, tag = self._name_by_puuid.get(puuid, (f"Player{puuid[-4:]}", "SIM"))
        return AccountDTO(puuid=puuid, gameName=name, tagLine=tag)

    async def get_summoner_by_puuid(self, puuid: str, *, platform: str) -> SummonerDTO:
        rng = random.Random(stable_seed("summoner", puuid))
        return SummonerDTO(
            puuid=puuid,
            id=None,
            accountId=None,
            profileIconId=rng.randrange(1, 5000),
            revisionDate=1_700_000_000_000,
            summonerLevel=rng.randrange(60, 800),
        )

    async def get_league_entries(self, puuid: str, *, platform: str) -> list[LeagueEntryDTO]:
        skill = self.skill_of(puuid)
        tier, division, lp = rank_for_skill(skill)
        rng = random.Random(stable_seed("league", puuid))
        games = rng.randrange(90, 420)
        wins = int(games * (0.42 + 0.18 * skill))
        return [
            LeagueEntryDTO.model_validate(
                {
                    "queueType": "RANKED_SOLO_5x5",
                    "tier": tier,
                    "rank": division,
                    "leaguePoints": lp,
                    "wins": wins,
                    "losses": games - wins,
                    "hotStreak": rng.random() < 0.15,
                    "veteran": games > 300,
                    "inactive": False,
                    "freshBlood": games < 120,
                }
            )
        ]

    def skill_of(self, puuid: str) -> float:
        """Latent skill for an account — the ground truth the ML should recover."""
        return self._demo_skill.get(puuid, skill_for_puuid(puuid))

    # --- matches ----------------------------------------------------------

    async def get_match_ids(
        self,
        puuid: str,
        *,
        platform: str,
        start: int = 0,
        count: int = 20,
        queue: int | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
    ) -> list[str]:
        total = _match_count_for(puuid)
        prefix = platform.upper()
        ids = [
            f"{prefix}_{stable_seed('match', puuid, i) % 9_000_000_000 + 1_000_000_000}"
            for i in range(total)
        ]
        page = ids[start : start + count]
        for match_id in page:
            self._match_owner.setdefault(match_id, puuid)
        return page

    async def get_match(self, match_id: str, *, platform: str) -> MatchDTO:
        return MatchDTO.model_validate(self._simulate(match_id, platform).match)

    async def get_timeline(self, match_id: str, *, platform: str) -> TimelineDTO:
        return TimelineDTO.model_validate(self._simulate(match_id, platform).timeline)

    async def aclose(self) -> None:  # pragma: no cover - nothing to close
        return None

    # --- internals --------------------------------------------------------

    def _focus_for(self, match_id: str) -> str:
        owner = self._match_owner.get(match_id)
        if owner is not None:
            return owner
        # Never seen this id: anchor it to a synthetic account derived from the id
        # so the same id keeps producing the same game.
        anchor = f"sim-{stable_seed('anchor', match_id):019d}"[:40]
        self._match_owner[match_id] = anchor
        return anchor

    def _roster(self, match_id: str) -> tuple[list[SimPlayer], str, int]:
        focus = self._focus_for(match_id)
        seed = stable_seed(match_id, focus)
        rng = random.Random(seed)
        name, tag = self._name_by_puuid.get(focus, (f"Player{focus[-4:]}", "SIM"))
        players = build_roster(focus, name, tag, seed=seed, focus_skill=self.skill_of(focus))
        patch = rng.choice(self.patch_pool)
        # Spread games backwards over the last ~45 days so recency ordering works.
        start_ms = 1_726_000_000_000 - rng.randrange(0, 45) * 86_400_000
        return players, patch, start_ms

    def _simulate(self, match_id: str, platform: str):  # type: ignore[no-untyped-def]
        players, patch, start_ms = self._roster(match_id)
        simulator = MatchSimulator(
            match_id,
            platform,
            players,
            patch=patch,
            game_start_ms=start_ms,
            seed=stable_seed(match_id),
        )
        return simulator.simulate()

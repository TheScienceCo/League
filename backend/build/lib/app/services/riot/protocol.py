"""The interface every Riot data source implements."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.services.riot.dto import (
    AccountDTO,
    LeagueEntryDTO,
    MatchDTO,
    SummonerDTO,
    TimelineDTO,
)


@runtime_checkable
class RiotProvider(Protocol):
    """Read-only access to the public Riot endpoints this project uses.

    Deliberately narrow: everything the platform does is post-game analysis of
    data a player could already see in their own match history, so the interface
    exposes no live-game, spectator, or in-progress endpoints at all. That is a
    design constraint, not an oversight — see `docs/COMPLIANCE.md`.
    """

    async def get_account_by_riot_id(
        self, game_name: str, tag_line: str, *, platform: str
    ) -> AccountDTO:
        """Resolve a Riot ID (``Name#TAG``) to a PUUID."""
        ...

    async def get_account_by_puuid(self, puuid: str, *, platform: str) -> AccountDTO: ...

    async def get_summoner_by_puuid(self, puuid: str, *, platform: str) -> SummonerDTO: ...

    async def get_league_entries(self, puuid: str, *, platform: str) -> list[LeagueEntryDTO]:
        """Ranked standing for every queue the player is placed in.

        Riot has changed the addressing of this endpoint (summoner-id -> PUUID);
        implementations are expected to encapsulate that and may legitimately
        return an empty list when standings are unavailable.
        """
        ...

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
    ) -> list[str]: ...

    async def get_match(self, match_id: str, *, platform: str) -> MatchDTO: ...

    async def get_timeline(self, match_id: str, *, platform: str) -> TimelineDTO: ...

    async def aclose(self) -> None: ...

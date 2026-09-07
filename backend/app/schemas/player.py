from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.schemas.common import APIModel


class RankInfo(APIModel):
    queue_type: str
    tier: str | None = None
    division: str | None = None
    league_points: int = 0
    wins: int = 0
    losses: int = 0
    rank_score: float = 0.0
    tier_group: str = "UNRANKED"
    hot_streak: bool = False

    @property
    def games(self) -> int:
        return self.wins + self.losses


class PlayerSummary(APIModel):
    puuid: str
    game_name: str | None = None
    tag_line: str | None = None
    platform: str
    profile_icon_id: int | None = None
    summoner_level: int | None = None
    last_ingested_at: datetime | None = None
    ranks: list[RankInfo] = Field(default_factory=list)


class RoleSplit(APIModel):
    role: str
    games: int
    wins: int
    win_rate: float
    champions: list[str] = Field(default_factory=list)


class ChampionSplit(APIModel):
    champion_id: int
    champion_name: str | None = None
    games: int
    wins: int
    win_rate: float
    kda: float
    cs_per_min: float


class PlayerProfile(APIModel):
    player: PlayerSummary
    games_analyzed: int
    win_rate: float | None = None
    primary_role: str | None = None
    tier_group: str = "UNRANKED"
    #: Headline derived metrics, averaged over analysed games.
    headline_metrics: list[MetricValue] = Field(default_factory=list)
    role_splits: list[RoleSplit] = Field(default_factory=list)
    champion_splits: list[ChampionSplit] = Field(default_factory=list)
    #: Standard deviation of a composite performance z-score across games.
    consistency: ConsistencyStats | None = None
    lead_conversion: LeadConversionStats | None = None


class MetricValue(APIModel):
    metric: str
    label: str
    value: float | None = None
    percentile: float | None = None
    cohort_median: float | None = None
    cohort_n: int | None = None
    higher_is_better: bool = True


class ConsistencyStats(APIModel):
    """How stable a player's game-to-game output is.

    `performance_std` is the standard deviation of a composite z-score built from
    the player's own cohort-normalised metrics; lower means more repeatable.
    """

    games: int
    performance_mean: float
    performance_std: float
    best_game_z: float
    worst_game_z: float
    #: Share of games within one standard deviation of the player's own mean.
    consistency_rate: float


class LeadConversionStats(APIModel):
    """How often a lead at 15 minutes turns into a win, and the reverse."""

    games_with_lead: int
    leads_converted: int
    lead_conversion_rate: float | None = None
    games_behind: int
    comebacks: int
    comeback_rate: float | None = None
    cohort_lead_conversion_rate: float | None = None


PlayerProfile.model_rebuild()

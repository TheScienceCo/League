"""Typed views over Riot API payloads.

These models are intentionally *partial*: they declare the fields the pipeline
actually consumes and allow everything else through (`extra="allow"`), so a
payload change upstream degrades to "field we do not read" rather than a hard
validation failure. Undocumented fields are never invented here — if a metric
needs something Riot does not publish, it is derived in the analytics layer and
labelled as an estimate.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RiotModel(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class AccountDTO(RiotModel):
    """`/riot/account/v1/accounts/by-riot-id/{gameName}/{tagLine}`"""

    puuid: str
    game_name: str | None = Field(default=None, alias="gameName")
    tag_line: str | None = Field(default=None, alias="tagLine")


class SummonerDTO(RiotModel):
    """`/lol/summoner/v4/summoners/by-puuid/{puuid}`

    `id`/`accountId` are optional: Riot has progressively restricted the
    encrypted summoner id, and nothing in this project requires it.
    """

    puuid: str
    id: str | None = None
    account_id: str | None = Field(default=None, alias="accountId")
    profile_icon_id: int | None = Field(default=None, alias="profileIconId")
    revision_date: int | None = Field(default=None, alias="revisionDate")
    summoner_level: int | None = Field(default=None, alias="summonerLevel")


class LeagueEntryDTO(RiotModel):
    """One entry from `/lol/league/v4/entries/by-puuid/{puuid}`."""

    queue_type: str = Field(alias="queueType")
    tier: str | None = None
    #: Riot calls the division "rank"; renamed to avoid colliding with our own
    #: notion of rank (tier + division + LP).
    division: str | None = Field(default=None, alias="rank")
    league_points: int = Field(default=0, alias="leaguePoints")
    wins: int = 0
    losses: int = 0
    hot_streak: bool = Field(default=False, alias="hotStreak")
    veteran: bool = False
    inactive: bool = False
    fresh_blood: bool = Field(default=False, alias="freshBlood")


class MatchMetadataDTO(RiotModel):
    match_id: str = Field(alias="matchId")
    data_version: str | None = Field(default=None, alias="dataVersion")
    participants: list[str] = Field(default_factory=list)


class ParticipantDTO(RiotModel):
    """A `info.participants[]` entry. Only consumed fields are declared."""

    puuid: str
    participant_id: int = Field(alias="participantId")
    team_id: int = Field(alias="teamId")
    win: bool = False

    riot_id_game_name: str | None = Field(default=None, alias="riotIdGameName")
    riot_id_tagline: str | None = Field(default=None, alias="riotIdTagline")
    summoner_name: str | None = Field(default=None, alias="summonerName")

    champion_id: int = Field(alias="championId")
    champion_name: str | None = Field(default=None, alias="championName")
    champ_level: int = Field(default=1, alias="champLevel")
    team_position: str = Field(default="", alias="teamPosition")
    individual_position: str | None = Field(default=None, alias="individualPosition")
    lane: str | None = None

    kills: int = 0
    deaths: int = 0
    assists: int = 0
    gold_earned: int = Field(default=0, alias="goldEarned")
    gold_spent: int = Field(default=0, alias="goldSpent")
    total_minions_killed: int = Field(default=0, alias="totalMinionsKilled")
    neutral_minions_killed: int = Field(default=0, alias="neutralMinionsKilled")

    total_damage_dealt_to_champions: int = Field(default=0, alias="totalDamageDealtToChampions")
    physical_damage_dealt_to_champions: int = Field(
        default=0, alias="physicalDamageDealtToChampions"
    )
    magic_damage_dealt_to_champions: int = Field(default=0, alias="magicDamageDealtToChampions")
    true_damage_dealt_to_champions: int = Field(default=0, alias="trueDamageDealtToChampions")
    total_damage_taken: int = Field(default=0, alias="totalDamageTaken")
    damage_self_mitigated: int = Field(default=0, alias="damageSelfMitigated")
    total_heals_on_teammates: int = Field(default=0, alias="totalHealsOnTeammates")
    damage_dealt_to_objectives: int = Field(default=0, alias="damageDealtToObjectives")
    damage_dealt_to_turrets: int = Field(default=0, alias="damageDealtToTurrets")

    vision_score: int = Field(default=0, alias="visionScore")
    wards_placed: int = Field(default=0, alias="wardsPlaced")
    wards_killed: int = Field(default=0, alias="wardsKilled")
    detector_wards_placed: int = Field(default=0, alias="detectorWardsPlaced")
    vision_wards_bought_in_game: int = Field(default=0, alias="visionWardsBoughtInGame")

    turret_takedowns: int = Field(default=0, alias="turretTakedowns")
    dragon_kills: int = Field(default=0, alias="dragonKills")
    baron_kills: int = Field(default=0, alias="baronKills")
    objectives_stolen: int = Field(default=0, alias="objectivesStolen")

    time_ccing_others: int = Field(default=0, alias="timeCCingOthers")
    total_time_spent_dead: int = Field(default=0, alias="totalTimeSpentDead")
    longest_time_spent_living: int = Field(default=0, alias="longestTimeSpentLiving")
    first_blood_kill: bool = Field(default=False, alias="firstBloodKill")
    first_tower_kill: bool = Field(default=False, alias="firstTowerKill")

    summoner1_id: int | None = Field(default=None, alias="summoner1Id")
    summoner2_id: int | None = Field(default=None, alias="summoner2Id")
    item0: int = 0
    item1: int = 0
    item2: int = 0
    item3: int = 0
    item4: int = 0
    item5: int = 0
    item6: int = 0
    perks: dict[str, Any] = Field(default_factory=dict)

    @property
    def items(self) -> list[int]:
        return [self.item0, self.item1, self.item2, self.item3, self.item4, self.item5, self.item6]

    @property
    def position(self) -> str:
        """Best available role label, preferring Riot's `teamPosition`."""
        return self.team_position or self.individual_position or "UNKNOWN"


class ObjectiveDTO(RiotModel):
    first: bool = False
    kills: int = 0


class ObjectivesDTO(RiotModel):
    baron: ObjectiveDTO = Field(default_factory=ObjectiveDTO)
    champion: ObjectiveDTO = Field(default_factory=ObjectiveDTO)
    dragon: ObjectiveDTO = Field(default_factory=ObjectiveDTO)
    inhibitor: ObjectiveDTO = Field(default_factory=ObjectiveDTO)
    rift_herald: ObjectiveDTO = Field(default_factory=ObjectiveDTO, alias="riftHerald")
    tower: ObjectiveDTO = Field(default_factory=ObjectiveDTO)


class TeamDTO(RiotModel):
    team_id: int = Field(alias="teamId")
    win: bool = False
    bans: list[dict[str, Any]] = Field(default_factory=list)
    objectives: ObjectivesDTO = Field(default_factory=ObjectivesDTO)


class MatchInfoDTO(RiotModel):
    game_id: int | None = Field(default=None, alias="gameId")
    game_creation: int | None = Field(default=None, alias="gameCreation")
    game_start_timestamp: int | None = Field(default=None, alias="gameStartTimestamp")
    game_end_timestamp: int | None = Field(default=None, alias="gameEndTimestamp")
    game_duration: int = Field(default=0, alias="gameDuration")
    game_mode: str | None = Field(default=None, alias="gameMode")
    game_type: str | None = Field(default=None, alias="gameType")
    game_version: str | None = Field(default=None, alias="gameVersion")
    map_id: int | None = Field(default=None, alias="mapId")
    platform_id: str | None = Field(default=None, alias="platformId")
    queue_id: int = Field(default=0, alias="queueId")
    participants: list[ParticipantDTO] = Field(default_factory=list)
    teams: list[TeamDTO] = Field(default_factory=list)


class MatchDTO(RiotModel):
    metadata: MatchMetadataDTO
    info: MatchInfoDTO


class PositionDTO(RiotModel):
    x: float = 0.0
    y: float = 0.0


class DamageStatsDTO(RiotModel):
    total_damage_done_to_champions: int = Field(default=0, alias="totalDamageDoneToChampions")
    total_damage_taken: int = Field(default=0, alias="totalDamageTaken")


class ParticipantFrameDTO(RiotModel):
    participant_id: int = Field(alias="participantId")
    current_gold: int = Field(default=0, alias="currentGold")
    total_gold: int = Field(default=0, alias="totalGold")
    level: int = 1
    xp: int = 0
    minions_killed: int = Field(default=0, alias="minionsKilled")
    jungle_minions_killed: int = Field(default=0, alias="jungleMinionsKilled")
    time_enemy_spent_controlled: int = Field(default=0, alias="timeEnemySpentControlled")
    position: PositionDTO | None = None
    damage_stats: DamageStatsDTO | None = Field(default=None, alias="damageStats")


class TimelineEventDTO(RiotModel):
    """Timeline events are a tagged union with dozens of variants.

    Rather than enumerate every variant we declare the shared/consumed keys and
    retain the full payload, which keeps ingestion resilient to Riot adding new
    event types (as it does most seasons).
    """

    timestamp: int = 0
    type: str = "UNKNOWN"
    participant_id: int | None = Field(default=None, alias="participantId")
    killer_id: int | None = Field(default=None, alias="killerId")
    victim_id: int | None = Field(default=None, alias="victimId")
    assisting_participant_ids: list[int] = Field(
        default_factory=list, alias="assistingParticipantIds"
    )
    team_id: int | None = Field(default=None, alias="teamId")
    position: PositionDTO | None = None
    monster_type: str | None = Field(default=None, alias="monsterType")
    monster_sub_type: str | None = Field(default=None, alias="monsterSubType")
    building_type: str | None = Field(default=None, alias="buildingType")
    tower_type: str | None = Field(default=None, alias="towerType")
    lane_type: str | None = Field(default=None, alias="laneType")
    ward_type: str | None = Field(default=None, alias="wardType")
    creator_id: int | None = Field(default=None, alias="creatorId")
    item_id: int | None = Field(default=None, alias="itemId")
    kill_type: str | None = Field(default=None, alias="killType")
    bounty: int | None = None
    shutdown_bounty: int | None = Field(default=None, alias="shutdownBounty")


class TimelineFrameDTO(RiotModel):
    timestamp: int = 0
    participant_frames: dict[str, ParticipantFrameDTO] = Field(
        default_factory=dict, alias="participantFrames"
    )
    events: list[TimelineEventDTO] = Field(default_factory=list)


class TimelineParticipantDTO(RiotModel):
    participant_id: int = Field(alias="participantId")
    puuid: str


class TimelineInfoDTO(RiotModel):
    frame_interval: int = Field(default=60000, alias="frameInterval")
    frames: list[TimelineFrameDTO] = Field(default_factory=list)
    participants: list[TimelineParticipantDTO] = Field(default_factory=list)
    game_id: int | None = Field(default=None, alias="gameId")


class TimelineDTO(RiotModel):
    metadata: MatchMetadataDTO
    info: TimelineInfoDTO

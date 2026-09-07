"""The mock provider must satisfy the same contract as the live client."""

from __future__ import annotations

import pytest

from app.core.constants import SR_QUEUES
from app.core.errors import NotFoundError
from app.services.riot.mock import MockRiotProvider, mock_puuid_for
from app.services.riot.protocol import RiotProvider
from app.services.riot.simulation import (
    encode_sim_puuid,
    rank_for_skill,
    skill_for_puuid,
)


def test_mock_satisfies_the_provider_protocol(provider: MockRiotProvider) -> None:
    assert isinstance(provider, RiotProvider)


async def test_riot_id_resolves_deterministically(provider: MockRiotProvider) -> None:
    first = await provider.get_account_by_riot_id("Someone", "NA1", platform="na1")
    second = await provider.get_account_by_riot_id("Someone", "NA1", platform="na1")
    assert first.puuid == second.puuid == mock_puuid_for("Someone", "NA1")


async def test_malformed_riot_id_is_rejected(provider: MockRiotProvider) -> None:
    with pytest.raises(NotFoundError):
        await provider.get_account_by_riot_id("NoTag", "", platform="na1")


async def test_match_payloads_are_deterministic(provider: MockRiotProvider) -> None:
    account = await provider.get_account_by_riot_id("Determinism", "NA1", platform="na1")
    ids = await provider.get_match_ids(account.puuid, platform="na1", count=3)
    first = await provider.get_match(ids[0], platform="na1")
    second = await provider.get_match(ids[0], platform="na1")
    assert first.model_dump() == second.model_dump()


async def test_match_shape_is_well_formed(provider: MockRiotProvider) -> None:
    account = await provider.get_account_by_riot_id("Shape", "NA1", platform="na1")
    ids = await provider.get_match_ids(account.puuid, platform="na1", count=1)
    match = await provider.get_match(ids[0], platform="na1")

    assert match.info.queue_id in SR_QUEUES
    assert len(match.info.participants) == 10
    assert {t.team_id for t in match.info.teams} == {100, 200}
    # Exactly one winning team.
    assert sum(1 for t in match.info.teams if t.win) == 1
    # Every role filled once per team.
    for team_id in (100, 200):
        roles = [p.position for p in match.info.participants if p.team_id == team_id]
        assert sorted(roles) == sorted({"TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"})
    assert 15 * 60 <= match.info.game_duration <= 50 * 60


async def test_timeline_frames_are_unique_and_monotone(provider: MockRiotProvider) -> None:
    account = await provider.get_account_by_riot_id("Timeline", "NA1", platform="na1")
    ids = await provider.get_match_ids(account.puuid, platform="na1", count=4)
    for match_id in ids:
        timeline = await provider.get_timeline(match_id, platform="na1")
        seen: set[tuple[int, int]] = set()
        last = -1
        for frame in timeline.info.frames:
            assert frame.timestamp >= last
            last = frame.timestamp
            for pf in frame.participant_frames.values():
                key = (pf.participant_id, frame.timestamp)
                assert key not in seen, "duplicate frame would violate the unique constraint"
                seen.add(key)


async def test_cumulative_frame_values_never_decrease(provider: MockRiotProvider) -> None:
    account = await provider.get_account_by_riot_id("Cumulative", "NA1", platform="na1")
    ids = await provider.get_match_ids(account.puuid, platform="na1", count=1)
    timeline = await provider.get_timeline(ids[0], platform="na1")

    previous: dict[int, tuple[int, int, int]] = {}
    for frame in timeline.info.frames:
        for pf in frame.participant_frames.values():
            current = (pf.total_gold, pf.xp, pf.minions_killed)
            if pf.participant_id in previous:
                assert all(
                    c >= p for c, p in zip(current, previous[pf.participant_id], strict=True)
                )
            previous[pf.participant_id] = current


async def test_positions_stay_on_the_map(provider: MockRiotProvider) -> None:
    account = await provider.get_account_by_riot_id("Bounds", "NA1", platform="na1")
    ids = await provider.get_match_ids(account.puuid, platform="na1", count=2)
    for match_id in ids:
        timeline = await provider.get_timeline(match_id, platform="na1")
        for frame in timeline.info.frames:
            for pf in frame.participant_frames.values():
                assert pf.position is not None
                assert -2000 <= pf.position.x <= 17000
                assert -2000 <= pf.position.y <= 17000


async def test_league_entry_matches_the_simulated_skill(provider: MockRiotProvider) -> None:
    """Rank must reflect how the player actually plays.

    Peers get their skill assigned before they have an identity; if the provider
    later derived their rank independently, every rank-conditioned analysis
    downstream would be fitting noise.
    """
    puuid = encode_sim_puuid(0.78, "test", 1)
    entries = await provider.get_league_entries(puuid, platform="na1")
    expected_tier, _, _ = rank_for_skill(0.78)
    assert entries[0].tier == expected_tier
    assert skill_for_puuid(puuid) == pytest.approx(0.78, abs=1e-4)


def test_skill_survives_the_puuid_round_trip() -> None:
    for skill in (0.02, 0.25, 0.5, 0.755, 0.985):
        assert skill_for_puuid(encode_sim_puuid(skill, "x")) == pytest.approx(skill, abs=1e-4)


def test_unencoded_puuids_fall_back_to_a_stable_distribution() -> None:
    values = [skill_for_puuid(f"riot-real-{i}") for i in range(200)]
    assert all(0.0 < v < 1.0 for v in values)
    assert skill_for_puuid("riot-real-1") == skill_for_puuid("riot-real-1")
    assert len(set(values)) > 150  # not degenerate

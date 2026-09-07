"""API contract tests against a seeded database."""

from __future__ import annotations

from sqlalchemy import select

from app.db.models import Match, MatchParticipant


def test_health_reports_dependencies(client) -> None:  # type: ignore[no-untyped-def]
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] is True
    assert body["riot_provider"] == "simulated"


def test_player_search_resolves_and_persists(client) -> None:  # type: ignore[no-untyped-def]
    response = client.get(
        "/api/v1/players/search", params={"riot_id": "ApiTest#NA1", "platform": "na1"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["game_name"] == "ApiTest"
    assert body["tag_line"] == "NA1"
    assert body["puuid"]


def test_malformed_riot_id_is_a_clean_error(client) -> None:  # type: ignore[no-untyped-def]
    response = client.get(
        "/api/v1/players/search", params={"riot_id": "NoTagHere", "platform": "na1"}
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_unknown_platform_is_rejected(client) -> None:  # type: ignore[no-untyped-def]
    response = client.get("/api/v1/players/search", params={"riot_id": "A#B", "platform": "mars1"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_unknown_player_profile_is_404(client) -> None:  # type: ignore[no-untyped-def]
    response = client.get("/api/v1/players/does-not-exist")
    assert response.status_code == 404
    assert "error" in response.json()


def test_profile_and_matches(client, seeded_db) -> None:  # type: ignore[no-untyped-def]
    puuid = seeded_db.scalar(select(MatchParticipant.puuid))
    profile = client.get(f"/api/v1/players/{puuid}")
    assert profile.status_code == 200
    body = profile.json()
    assert body["games_analyzed"] > 0
    assert body["player"]["puuid"] == puuid
    assert isinstance(body["headline_metrics"], list)

    matches = client.get(f"/api/v1/players/{puuid}/matches", params={"limit": 5})
    assert matches.status_code == 200
    page = matches.json()
    assert page["total"] >= len(page["items"])
    for item in page["items"]:
        assert item["match_id"]
        assert item["team_position"]


def test_match_analysis_requires_a_participant(client, seeded_db) -> None:  # type: ignore[no-untyped-def]
    match_id = seeded_db.scalar(select(Match.match_id))
    response = client.get(
        f"/api/v1/matches/{match_id}", params={"puuid": "someone-who-did-not-play"}
    )
    assert response.status_code == 404


def test_match_analysis_payload_is_complete(client, seeded_db) -> None:  # type: ignore[no-untyped-def]
    row = seeded_db.execute(
        select(MatchParticipant.match_id, MatchParticipant.puuid).limit(1)
    ).one()
    response = client.get(f"/api/v1/matches/{row.match_id}", params={"puuid": row.puuid})
    assert response.status_code == 200
    body = response.json()

    assert body["match"]["match_id"] == row.match_id
    assert body["player"]["puuid"] == row.puuid
    assert len(body["participants"]) == 10
    assert len(body["timeline"]) > 0
    assert isinstance(body["deaths"], list)
    assert isinstance(body["objective_setups"], list)
    assert isinstance(body["roams"], list)
    assert isinstance(body["advanced_metrics"], list)

    # The timeline carries the derived differentials, not just raw totals.
    point = body["timeline"][-1]
    assert {"minute", "gold", "xp", "cs", "gold_diff", "team_gold_diff"} <= set(point)


def test_advanced_stats_needs_ingested_games(client) -> None:  # type: ignore[no-untyped-def]
    response = client.get("/api/v1/players/nobody/advanced")
    assert response.status_code == 404


def test_skill_gap_reports_missing_model_clearly(client, seeded_db) -> None:  # type: ignore[no-untyped-def]
    """With no trained model the API must say so, not return zeros."""
    puuid = seeded_db.scalar(select(MatchParticipant.puuid))
    response = client.get(f"/api/v1/players/{puuid}/skill-gap")
    assert response.status_code == 409
    body = response.json()
    assert body["error"]["code"] == "insufficient_data"
    assert "train" in body["error"]["message"].lower()


def test_spatial_endpoints_carry_a_disclaimer(client) -> None:  # type: ignore[no-untyped-def]
    """Model-derived figures must always be labelled as estimates."""
    heatmap = client.get("/api/v1/spatial/heatmap", params={"role": "MIDDLE"})
    assert heatmap.status_code == 200
    assert "association" in heatmap.json()["disclaimer"].lower()

    zones = client.get("/api/v1/spatial/zones", params={"role": "MIDDLE"})
    assert zones.status_code == 200
    assert zones.json()["disclaimer"]


def test_ingest_requires_an_identifier(client) -> None:  # type: ignore[no-untyped-def]
    response = client.post("/api/v1/ingest", json={"platform": "na1", "count": 5})
    assert response.status_code == 422


def test_ingest_job_lifecycle(client) -> None:  # type: ignore[no-untyped-def]
    response = client.post(
        "/api/v1/ingest",
        json={"riot_id": "JobTest#NA1", "platform": "na1", "count": 2},
    )
    assert response.status_code == 202
    job = response.json()
    assert job["id"]
    assert job["status"] in {"PENDING", "RUNNING", "SUCCEEDED", "PARTIAL"}

    polled = client.get(f"/api/v1/ingest/{job['id']}")
    assert polled.status_code == 200
    assert polled.json()["id"] == job["id"]

    assert client.get("/api/v1/ingest/no-such-job").status_code == 404


def test_openapi_documents_every_route(client) -> None:  # type: ignore[no-untyped-def]
    schema = client.get("/openapi.json").json()
    paths = set(schema["paths"])
    expected = {
        "/api/v1/health",
        "/api/v1/players/search",
        "/api/v1/players/{puuid}",
        "/api/v1/players/{puuid}/matches",
        "/api/v1/players/{puuid}/advanced",
        "/api/v1/players/{puuid}/cohort",
        "/api/v1/players/{puuid}/spatial",
        "/api/v1/players/{puuid}/skill-gap",
        "/api/v1/matches/{match_id}",
        "/api/v1/spatial/heatmap",
        "/api/v1/spatial/zones",
        "/api/v1/skill-gap/rank-separation",
        "/api/v1/ingest",
    }
    assert expected <= paths

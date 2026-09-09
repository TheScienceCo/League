"""API surface."""

from __future__ import annotations

from app.services.parser.types import Availability


class TestHealth:
    def test_reports_dependencies(self, client):
        body = client.get("/api/v1/health").json()
        assert body["status"] in {"ok", "degraded"}
        assert body["replay_parser"] == "mgz"
        assert "database" in body and "redis" in body


class TestUpload:
    def test_upload_returns_analysis(self, client, rec_with_queue):
        r = client.post("/api/v1/replays", files={"file": ("game.aoe2record", rec_with_queue)})
        assert r.status_code == 201
        body = r.json()
        assert body["map_name"] == "Socotra"
        assert len(body["replay_id"]) == 64
        assert len(body["players"]) == 2
        for p in body["players"]:
            assert p["name"] and p["civilization"]
            assert p["resource_curve"]
            assert p["insights"]
            assert p["metrics"]["feudal_time"]["availability"] == Availability.OBSERVED

    def test_upload_is_idempotent(self, client, rec_with_queue):
        f = {"file": ("game.aoe2record", rec_with_queue)}
        first = client.post("/api/v1/replays", files=f).json()
        second = client.post(
            "/api/v1/replays", files={"file": ("other.aoe2record", rec_with_queue)}
        ).json()
        assert first["replay_id"] == second["replay_id"]

    def test_analysis_is_retrievable(self, client, rec_with_queue):
        rid = client.post(
            "/api/v1/replays", files={"file": ("g.aoe2record", rec_with_queue)}
        ).json()["replay_id"]
        got = client.get(f"/api/v1/replays/{rid}")
        assert got.status_code == 200
        assert got.json()["replay_id"] == rid

    def test_upload_appears_in_listing(self, client, rec_with_queue):
        client.post("/api/v1/replays", files={"file": ("g.aoe2record", rec_with_queue)})
        listing = client.get("/api/v1/replays").json()
        assert len(listing) == 1
        assert listing[0]["map_name"] == "Socotra"
        assert set(listing[0]["players"]) == {"NOT", "El_Matador"}

    def test_warnings_surface_to_caller(self, client, rec_without_queue):
        body = client.post(
            "/api/v1/replays", files={"file": ("g.aoe2record", rec_without_queue)}
        ).json()
        assert any("queue" in w.lower() for w in body["warnings"])


class TestUploadErrors:
    def test_rejects_wrong_extension(self, client):
        r = client.post("/api/v1/replays", files={"file": ("notes.txt", b"hello")})
        assert r.status_code == 415

    def test_rejects_empty_file(self, client):
        r = client.post("/api/v1/replays", files={"file": ("g.aoe2record", b"")})
        assert r.status_code == 400

    def test_unparseable_file_explains_itself(self, client):
        r = client.post("/api/v1/replays", files={"file": ("g.aoe2record", b"not a replay")})
        assert r.status_code == 422
        assert "could not parse" in r.json()["detail"].lower()

    def test_unknown_id_is_404(self, client):
        assert client.get("/api/v1/replays/" + "0" * 64).status_code == 404


class TestPersistence:
    def test_upload_is_indexed_for_querying(self, client, session, rec_with_queue):
        from sqlalchemy import select

        from app.db.models import Replay, ReplayPlayer

        client.post("/api/v1/replays", files={"file": ("g.aoe2record", rec_with_queue)})
        replay = session.scalar(select(Replay))
        assert replay is not None and replay.map_name == "Socotra"

        names = set(session.scalars(select(ReplayPlayer.name)))
        assert names == {"NOT", "El_Matador"}
        assert all(p.feudal_ms for p in replay.players)

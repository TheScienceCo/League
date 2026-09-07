"""Riot API access layer.

Everything downstream depends on `RiotProvider` (a Protocol), never on the
concrete HTTP client. That gives us three things: the ingestion pipeline is
unit-testable without network access, the app is fully runnable without an API
key via `MockRiotProvider`, and any endpoint whose exact shape we are unsure of
can be stubbed behind the same interface rather than guessed at.
"""

from app.services.riot.factory import get_riot_provider
from app.services.riot.protocol import RiotProvider

__all__ = ["RiotProvider", "get_riot_provider"]

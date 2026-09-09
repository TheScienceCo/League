"""Plain-language observations derived from measured values.

Every line this produces cites a number that was actually measured. There is no
generic advice here ("improve your economy"): if we cannot measure it, we do not
say anything about it.

These are observations, not causal claims. A player who floated resources and
lost did not necessarily lose *because* they floated.
"""

from __future__ import annotations

from app.services.analysis.metrics import MatchAnalysis, PlayerAnalysis
from app.services.parser.types import Availability


class MetricStub:
    """Stand-in so a missing metric compares as not-known."""

    is_known = False
    value = None


def _clock(ms: int) -> str:
    total = ms // 1000
    return f"{total // 60}:{total % 60:02d}"


def _signed_clock(ms: int) -> str:
    return ("-" if ms < 0 else "+") + _clock(abs(ms))


def for_player(analysis: MatchAnalysis, player: PlayerAnalysis) -> list[str]:
    out: list[str] = []
    m = player.metrics

    # --- Age timings ------------------------------------------------------
    for age in ("feudal", "castle", "imperial"):
        t, d = m.get(f"{age}_time"), m.get(f"{age}_delta")
        if t and t.is_known:
            line = f"Reached {age.title()} Age at {_clock(int(t.value))}"
            if d and d.is_known:
                delta = int(d.value)
                if delta < 0:
                    line += f", {_clock(-delta)} ahead of your opponent."
                elif delta > 0:
                    line += f", {_clock(delta)} behind your opponent."
                else:
                    line += ", level with your opponent."
            else:
                line += "."
            out.append(line)

    # --- Floating ---------------------------------------------------------
    peak, floating = m.get("float_peak"), m.get("time_floating")
    if peak and peak.is_known and floating and floating.is_known and int(floating.value) > 0:
        out.append(
            f"Spent {_clock(int(floating.value))} holding more than 1000 banked "
            f"resources, peaking at {int(peak.value)}. Resources in the bank are "
            f"not doing anything; that peak is roughly a Town Center plus change."
        )
    if player.float_by_age:
        worst = max(player.float_by_age.items(), key=lambda kv: kv[1])
        if worst[1] > 700:
            out.append(
                f"Banked resources averaged {worst[1]} during {worst[0].title()} Age — "
                f"your least efficient phase of the game."
            )

    # --- Production -------------------------------------------------------
    gap = m.get("max_production_gap")
    if gap and gap.is_known and int(gap.value) > 60_000:
        out.append(
            f"Longest gap between villager queue commands was {_clock(int(gap.value))}. "
            f"At roughly 25s per villager that is about {int(gap.value) // 25000} "
            f"villagers of lost production, though a full queue can mask a real gap."
        )
    elif gap and gap.availability is Availability.UNAVAILABLE:
        out.append(
            "Production metrics are unavailable for this replay version — the "
            "unit-queue commands could not be decoded."
        )

    # --- Tempo / activity -------------------------------------------------
    eapm = m.get("eapm")
    if eapm and eapm.is_known:
        others = [
            int(o.metrics["eapm"].value)
            for o in analysis.players
            if o.player_number != player.player_number
            and o.metrics.get("eapm", MetricStub()).is_known
        ]
        if others:
            gap_apm = int(eapm.value) - max(others)
            if gap_apm <= -20:
                out.append(
                    f"Your effective APM was {int(eapm.value)} against {max(others)} — "
                    f"you issued substantially fewer meaningful commands than your opponent."
                )
            elif gap_apm >= 20:
                out.append(
                    f"Your effective APM was {int(eapm.value)} against {max(others)}, "
                    f"a clear activity advantage."
                )

    if player.opening and player.opening != "unclassified":
        if player.opening == "fast castle":
            out.append(
                f"No military production building before Castle Age at "
                f"{_clock(player.opening_evidence_ms or 0)} — read as a fast castle."
            )
        elif player.opening_evidence_ms is not None:
            out.append(
                f"Opening read as {player.opening}: first military production "
                f"building placed at {_clock(player.opening_evidence_ms)}."
            )

    return out


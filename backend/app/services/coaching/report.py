"""Generate coaching reports from match analysis."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.core.logging import get_logger
from app.schemas.aoe2 import CoachingReportInsight, CoachingReportResponse
from app.services.analytics.metrics import PlayerMetrics

log = get_logger(__name__)


class CoachingReportGenerator:
    """Generate comprehensive coaching reports for matches."""

    def __init__(self):
        """Initialize the report generator."""
        pass

    def generate_report(
        self,
        match_id: int,
        player_id: int,
        metrics: PlayerMetrics,
        events: list[dict[str, Any]],
        opponent_metrics: dict[int, PlayerMetrics] | None = None,
    ) -> CoachingReportResponse:
        """
        Generate a comprehensive coaching report for a match.

        Args:
            match_id: Match ID
            player_id: Player ID
            metrics: Calculated metrics for this player
            events: Events for this player
            opponent_metrics: Optional metrics for opponents for comparison

        Returns:
            Complete coaching report
        """
        report = CoachingReportResponse(
            match_id=match_id,
            player_id=player_id,
            generated_at=datetime.utcnow(),
            summary="",
            what_went_well=[],
            biggest_mistakes=[],
            actionable_improvements=[],
            overall_grade="B",
            estimated_elo_performance=1600,
        )

        # Identify strengths
        report.what_went_well = self._identify_strengths(metrics)

        # Identify mistakes
        report.biggest_mistakes = self._identify_mistakes(metrics, events)

        # Generate recommendations
        report.actionable_improvements = self._generate_recommendations(
            metrics, events, opponent_metrics
        )

        # Overall summary
        report.summary = self._generate_summary(
            metrics, report.what_went_well, report.biggest_mistakes
        )

        # Estimate performance level
        report.estimated_elo_performance = self._estimate_elo_performance(metrics)

        # Grade
        report.overall_grade = self._assign_grade(metrics, events)

        log.info(
            "Coaching report generated",
            match_id=match_id,
            player_id=player_id,
            grade=report.overall_grade,
        )

        return report

    def _identify_strengths(self, metrics: PlayerMetrics) -> list[CoachingReportInsight]:
        """Identify what the player did well."""
        strengths = []

        # Check economy metrics
        if metrics.villager_production_uptime and metrics.villager_production_uptime > 70:
            strengths.append(
                CoachingReportInsight(
                    category="economy",
                    title="Strong Villager Production",
                    description=f"Your villager production uptime was {metrics.villager_production_uptime:.1f}%, which is above average.",
                    magnitude=metrics.villager_production_uptime,
                    evidence_text="Town Center remained busy throughout the game",
                    estimated_impact="+3-5% economy rating",
                )
            )

        # Check military metrics
        if (
            metrics.military_value_killed
            and metrics.military_value_lost
            and metrics.military_value_killed > metrics.military_value_lost * 1.3
        ):
            strengths.append(
                CoachingReportInsight(
                    category="military",
                    title="Excellent Engagement Efficiency",
                    description=f"You killed {metrics.military_value_killed:.0f} resource value while losing {metrics.military_value_lost:.0f}.",
                    magnitude=metrics.military_value_killed / max(metrics.military_value_lost, 1),
                    evidence_text="Strong tactical execution in battles",
                    estimated_impact="+5-8% military rating",
                )
            )

        # Check build order
        if metrics.age_up_timing_ms:
            feudal_ms = metrics.age_up_timing_ms.get("feudal", 0)
            if feudal_ms > 0 and feudal_ms < 11 * 60 * 1000:  # Before 11:00
                strengths.append(
                    CoachingReportInsight(
                        category="build",
                        title="Fast Castle Progression",
                        description=f"You reached Feudal Age in {feudal_ms // 60000}:{feudal_ms % 60000 // 1000:02d}, which is ahead of many players.",
                        magnitude=float(feudal_ms),
                        evidence_text="Strong early economic planning",
                    )
                )

        return strengths[:3]  # Top 3 strengths

    def _identify_mistakes(
        self, metrics: PlayerMetrics, events: list[dict[str, Any]]
    ) -> list[CoachingReportInsight]:
        """Identify biggest mistakes and costly errors."""
        mistakes = []

        # Check TC idle time
        if metrics.tc_idle_time_ms and metrics.tc_idle_time_ms > 3 * 60 * 1000:  # 3+ minutes
            minutes = metrics.tc_idle_time_ms // 60000
            seconds = (metrics.tc_idle_time_ms % 60000) // 1000
            missed_villagers = metrics.tc_idle_time_ms // 25000  # Rough villager production time
            mistakes.append(
                CoachingReportInsight(
                    category="economy",
                    title="Significant Town Center Idle Time",
                    description=f"Your TC was idle for approximately {minutes}m {seconds}s.",
                    magnitude=float(metrics.tc_idle_time_ms),
                    evidence_text=f"This is equivalent to approximately {int(missed_villagers)} missing villagers.",
                    recommendation="Always keep your TC producing. Queue up villagers before running out of food.",
                    estimated_impact="-5-8% economy efficiency",
                )
            )

        # Check resource float peaks
        if metrics.resource_float_peak and metrics.resource_float_peak > 1200:
            mistakes.append(
                CoachingReportInsight(
                    category="economy",
                    title="High Resource Waste (Floating Resources)",
                    description=f"You had up to {metrics.resource_float_peak:.0f} unspent resources at one time.",
                    magnitude=metrics.resource_float_peak,
                    evidence_text="Resources sitting in your base don't win games; they need to become military or structures.",
                    recommendation="Spend resources faster. Consider additional TCs or aggressive army production.",
                    estimated_impact="-3-6% win probability",
                )
            )

        # Check reaction latency
        if metrics.reaction_latency_ms and metrics.reaction_latency_ms > 120000:  # 2+ minutes
            mistakes.append(
                CoachingReportInsight(
                    category="strategic",
                    title="Slow Strategic Reaction",
                    description=f"After enemy actions, you took {metrics.reaction_latency_ms // 60000}m+ to respond.",
                    magnitude=float(metrics.reaction_latency_ms),
                    evidence_text="Delayed responses allow opponents to consolidate advantages.",
                    recommendation="Scout more frequently. Watch your opponent's TC and production buildings.",
                    estimated_impact="-4-7% decision quality",
                )
            )

        return mistakes[:3]  # Top 3 mistakes

    def _generate_recommendations(
        self,
        metrics: PlayerMetrics,
        events: list[dict[str, Any]],
        opponent_metrics: dict[int, PlayerMetrics] | None = None,
    ) -> list[CoachingReportInsight]:
        """Generate actionable improvement recommendations."""
        recommendations = []

        # Always include economy improvement if there's floating
        if metrics.resource_float_average and metrics.resource_float_average > 200:
            recommendations.append(
                CoachingReportInsight(
                    category="economy",
                    title="Practice Resource Management",
                    description="Reducing floating resources is one of the fastest ways to improve.",
                    recommendation="In your next games, aim to keep resources under 500 at all times. This requires planning military/buildings ahead of time.",
                    estimated_impact="+5-10% win rate",
                )
            )

        # Military efficiency
        if (
            metrics.military_production_uptime
            and metrics.military_production_uptime < 50
        ):
            recommendations.append(
                CoachingReportInsight(
                    category="military",
                    title="Increase Military Production",
                    description="You had low military production building uptime.",
                    recommendation="Build more production buildings (Ranges, Stables, Barracks). Don't wait to be under attack to build military.",
                    estimated_impact="+3-8% win rate",
                )
            )

        # Scouting
        if metrics.scouting_coverage_percent and metrics.scouting_coverage_percent < 50:
            recommendations.append(
                CoachingReportInsight(
                    category="scouting",
                    title="Improve Early Scouting",
                    description="Early map information is critical for decision-making.",
                    recommendation="Train 1-2 scout cavalry immediately after Feudal Age and never let them sit idle.",
                    estimated_impact="+2-5% decision quality",
                )
            )

        return recommendations

    def _generate_summary(
        self,
        metrics: PlayerMetrics,
        strengths: list[CoachingReportInsight],
        mistakes: list[CoachingReportInsight],
    ) -> str:
        """Generate human-readable match summary."""
        parts = []

        if strengths:
            parts.append(f"Strengths: {', '.join(s.title for s in strengths[:2])}")

        if mistakes:
            parts.append(f"Areas to improve: {', '.join(m.title for m in mistakes[:2])}")

        summary = ". ".join(parts) + "."

        return summary

    def _estimate_elo_performance(self, metrics: PlayerMetrics) -> int:
        """Estimate Elo level based on metrics."""
        base_elo = 1400

        # Add for good economy
        if metrics.villager_production_uptime:
            base_elo += int((metrics.villager_production_uptime - 50) * 3)

        # Add for good military efficiency
        if metrics.engagement_efficiency:
            base_elo += int((metrics.engagement_efficiency - 40) * 2)

        # Subtract for high resource float
        if metrics.resource_float_average:
            base_elo -= int(metrics.resource_float_average / 300)

        # Subtract for high TC idle
        if metrics.tc_idle_time_ms:
            base_elo -= int(metrics.tc_idle_time_ms / 60000)

        return max(800, min(2400, base_elo))

    def _assign_grade(
        self, metrics: PlayerMetrics, events: list[dict[str, Any]]
    ) -> str:
        """Assign a letter grade (A-D) based on overall performance."""
        elo = self._estimate_elo_performance(metrics)

        if elo >= 1900:
            return "A"
        elif elo >= 1600:
            return "B"
        elif elo >= 1300:
            return "C"
        else:
            return "D"

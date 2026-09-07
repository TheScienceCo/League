import Link from "next/link";

import { RiftMap } from "@/components/rift-map";
import { Card, Disclaimer, EmptyState } from "@/components/ui";
import { api } from "@/lib/api";
import { formatPercent, PHASES, ROLES, roleLabel, TIER_GROUPS, tierLabel, zoneLabel } from "@/lib/format";
import type { HeatmapResponse, ZoneRiskResponse } from "@/lib/types";

export const dynamic = "force-dynamic";
export const metadata = { title: "Map risk" };

export default async function GlobalMapPage({
  searchParams,
}: {
  searchParams: Promise<{ role?: string; phase?: string; tier?: string }>;
}) {
  const { role, phase, tier } = await searchParams;
  const activeRole = role ?? "MIDDLE";
  const activePhase = phase ?? "EARLY";
  const activeTier = tier ?? "";

  let heatmap: HeatmapResponse | null = null;
  let zones: ZoneRiskResponse | null = null;
  try {
    [heatmap, zones] = await Promise.all([
      api.heatmap({
        role: activeRole,
        phase: activePhase,
        tier_group: activeTier || undefined,
        min_exposures: 8,
      }),
      api.zoneRisk({ role: activeRole, tier_group: activeTier || undefined, min_exposures: 30 }),
    ]);
  } catch {
    heatmap = null;
  }

  function href(next: { role?: string; phase?: string; tier?: string }) {
    const params = new URLSearchParams({
      role: next.role ?? activeRole,
      phase: next.phase ?? activePhase,
    });
    const t = next.tier ?? activeTier;
    if (t) params.set("tier", t);
    return `/map?${params.toString()}`;
  }

  const cells = (heatmap?.cells ?? []).map((cell) => ({
    cell_x: cell.cell_x,
    cell_y: cell.cell_y,
    intensity: cell.lift,
    exposures: cell.exposures,
    deaths: cell.deaths,
    zone: cell.zone,
    label: `${cell.lift.toFixed(2)}× baseline · ${formatPercent(cell.risk, 1)} risk`,
  }));

  const phaseZones = (zones?.zones ?? []).filter((z) => z.phase === activePhase);

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Map risk</h1>
        <p className="mt-2 max-w-3xl text-ink-muted">
          Every timeline frame is an exposure: a player, at a position, at a time.
          Each is labelled with whether that player died within{" "}
          {heatmap?.horizon_seconds ?? 30} seconds. Aggregating over a grid gives the
          probability of dying shortly after occupying each part of the map, and the
          ratio of that to the average position for the same role and phase.
        </p>
      </header>

      <Card title="Filters">
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="label w-14">Role</span>
            {ROLES.map((r) => (
              <Link
                key={r}
                href={href({ role: r })}
                className={`rounded border px-2.5 py-1 text-xs ${
                  r === activeRole
                    ? "border-accent bg-accent/15 text-accent"
                    : "border-surface-border text-ink-muted hover:border-accent"
                }`}
              >
                {roleLabel(r)}
              </Link>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="label w-14">Phase</span>
            {PHASES.map((p) => (
              <Link
                key={p}
                href={href({ phase: p })}
                className={`rounded border px-2.5 py-1 text-xs ${
                  p === activePhase
                    ? "border-accent bg-accent/15 text-accent"
                    : "border-surface-border text-ink-muted hover:border-accent"
                }`}
              >
                {p === "EARLY" ? "Early (0–14m)" : p === "MID" ? "Mid (14–25m)" : "Late (25m+)"}
              </Link>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="label w-14">Rank</span>
            <Link
              href={href({ tier: "" })}
              className={`rounded border px-2.5 py-1 text-xs ${
                !activeTier
                  ? "border-accent bg-accent/15 text-accent"
                  : "border-surface-border text-ink-muted hover:border-accent"
              }`}
            >
              All
            </Link>
            {TIER_GROUPS.map((t) => (
              <Link
                key={t}
                href={href({ tier: t })}
                className={`rounded border px-2.5 py-1 text-xs ${
                  t === activeTier
                    ? "border-accent bg-accent/15 text-accent"
                    : "border-surface-border text-ink-muted hover:border-accent"
                }`}
              >
                {tierLabel(t)}
              </Link>
            ))}
          </div>
        </div>
      </Card>

      {!heatmap || cells.length === 0 ? (
        <EmptyState title="No risk surface for this selection">
          The grid needs enough observations per cell. Try a broader filter, or
          ingest more matches.
        </EmptyState>
      ) : (
        <div className="grid gap-5 lg:grid-cols-2">
          <Card
            title={`${roleLabel(activeRole)} · ${activePhase.toLowerCase()} game`}
            subtitle="Colour is risk relative to the average position for this role and phase."
          >
            <RiftMap cells={cells} gridSize={heatmap.grid_size} legendLabel="Risk vs baseline" />
          </Card>

          <Card
            title="Dangerous regions"
            subtitle="Ranked by how much more likely a death is after being present."
          >
            {phaseZones.length === 0 ? (
              <p className="text-sm text-ink-muted">Not enough observations for this phase.</p>
            ) : (
              <ul className="space-y-3">
                {phaseZones.slice(0, 6).map((zone) => (
                  <li key={`${zone.zone}-${zone.phase}`}>
                    <div className="flex items-baseline justify-between gap-3">
                      <span className="font-medium">{zoneLabel(zone.zone)}</span>
                      <span
                        className={`stat text-sm ${
                          zone.lift > 1.25 ? "text-bad" : zone.lift < 0.8 ? "text-good" : ""
                        }`}
                      >
                        {zone.lift.toFixed(2)}×
                      </span>
                    </div>
                    {zone.insight && (
                      <p className="mt-0.5 text-xs leading-relaxed text-ink-muted">
                        {zone.insight}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      )}

      {heatmap && <Disclaimer>{heatmap.disclaimer}</Disclaimer>}
    </div>
  );
}

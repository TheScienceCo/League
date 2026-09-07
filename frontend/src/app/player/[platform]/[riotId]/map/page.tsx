import { RiftMap } from "@/components/rift-map";
import { Card, Disclaimer, EmptyState, PlayerTabs, Stat } from "@/components/ui";
import { api } from "@/lib/api";
import { formatPercent, tierLabel, zoneLabel } from "@/lib/format";
import type { PlayerSpatial } from "@/lib/types";

import { PlayerHeader } from "../player-header";
import { resolvePlayer, type PlayerRouteParams } from "../player-data";

export const dynamic = "force-dynamic";

export default async function PlayerMapPage({
  params,
}: {
  params: Promise<PlayerRouteParams>;
}) {
  const routeParams = await params;
  const { player, riotId } = await resolvePlayer(routeParams);

  let spatial: PlayerSpatial | null = null;
  let profile = null;
  try {
    [spatial, profile] = await Promise.all([
      api.playerSpatial(player.puuid, 40),
      api.profile(player.puuid).catch(() => null),
    ]);
  } catch {
    spatial = null;
  }

  const cells = (spatial?.cells ?? []).map((cell) => ({
    cell_x: cell.cell_x,
    cell_y: cell.cell_y,
    intensity: cell.death_rate,
    exposures: cell.exposures,
    deaths: cell.deaths,
    label: `Death rate ${formatPercent(cell.death_rate, 1)}`,
  }));

  const exposureCells = (spatial?.cells ?? []).map((cell) => ({
    cell_x: cell.cell_x,
    cell_y: cell.cell_y,
    intensity: cell.exposures,
    exposures: cell.exposures,
    deaths: cell.deaths,
    label: `${cell.exposures} observations`,
  }));

  const markers = (spatial?.deaths ?? []).map((death) => ({
    x: death.x,
    y: death.y,
    label: `${death.zone} at ${death.minute}m`,
  }));

  return (
    <div>
      <PlayerHeader
        player={player}
        riotId={riotId}
        platform={routeParams.platform}
        profile={profile}
      />
      <PlayerTabs platform={routeParams.platform} riotId={riotId} active="map" />

      {!spatial || spatial.matches === 0 ? (
        <EmptyState title="No spatial data">
          Map analysis needs ingested timelines, which carry position samples once
          per minute.
        </EmptyState>
      ) : (
        <div className="space-y-5">
          <div className="grid gap-5 lg:grid-cols-2">
            <Card
              title="Where this player dies"
              subtitle={`Death rate per map cell across ${spatial.matches} games, with individual deaths marked.`}
            >
              <RiftMap
                cells={cells}
                markers={markers}
                gridSize={spatial.grid_size}
                legendLabel="Death rate"
                markerLabel="Deaths"
              />
            </Card>

            <Card
              title="Where this player spends time"
              subtitle="Position samples per cell — the denominator behind the death rate."
            >
              <RiftMap
                cells={exposureCells}
                gridSize={spatial.grid_size}
                legendLabel="Time spent"
              />
            </Card>
          </div>

          {spatial.comparison && (
            <div className="grid gap-5 lg:grid-cols-3">
              <Card title="Risk-adjusted positioning">
                <div className="space-y-4">
                  <Stat
                    label="Deaths above expectation"
                    value={
                      spatial.comparison.player_deaths_above_expected !== null
                        ? spatial.comparison.player_deaths_above_expected.toFixed(2)
                        : "—"
                    }
                    hint="per game, vs the risk model"
                    tone={
                      (spatial.comparison.player_deaths_above_expected ?? 0) > 0.5
                        ? "text-bad"
                        : (spatial.comparison.player_deaths_above_expected ?? 0) < -0.5
                          ? "text-good"
                          : ""
                    }
                  />
                  <Stat
                    label="Time in high-risk areas"
                    value={formatPercent(spatial.comparison.player_high_risk_share)}
                    hint="share of position samples"
                  />
                  <p className="text-xs leading-relaxed text-ink-faint">
                    A positive “deaths above expectation” means the player died more
                    often than the model expected given where and when they stood —
                    which points at what happened in those spots, not at the spots
                    themselves.
                  </p>
                </div>
              </Card>

              <Card
                className="lg:col-span-2"
                title={`Riskiest regions for ${tierLabel(spatial.comparison.reference_tier_group)}`}
                subtitle="Regions where being present is most associated with dying shortly afterwards."
              >
                <div className="scroll-x">
                  <table className="data">
                    <thead>
                      <tr>
                        <th>Region</th>
                        <th>Phase</th>
                        <th>Risk</th>
                        <th>vs baseline</th>
                        <th>Observations</th>
                      </tr>
                    </thead>
                    <tbody>
                      {spatial.comparison.zones.map((zone) => (
                        <tr key={`${zone.zone}-${zone.phase}`}>
                          <td>{zoneLabel(zone.zone)}</td>
                          <td className="text-ink-muted">{zone.phase}</td>
                          <td className="stat">{formatPercent(zone.risk, 1)}</td>
                          <td
                            className={`stat ${
                              zone.lift > 1.25 ? "text-bad" : zone.lift < 0.8 ? "text-good" : ""
                            }`}
                          >
                            {zone.lift.toFixed(2)}×
                          </td>
                          <td className="stat text-ink-faint">
                            {zone.exposures.toLocaleString()}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Card>
            </div>
          )}

          <Disclaimer>{spatial.disclaimer}</Disclaimer>
        </div>
      )}
    </div>
  );
}

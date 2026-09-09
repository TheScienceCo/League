"use client";

import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { clock } from "@/lib/format";
import type { PlayerAnalysis } from "@/lib/types";

/**
 * Categorical slots 1 and 2, validated for CVD separation and contrast against
 * both the light and dark chart surfaces. Colour follows the player, not their
 * rank, so the series keep their hues however the data is filtered.
 */
const SERIES = ["var(--series-1)", "var(--series-2)"];

const AGE_LABEL: Record<string, string> = {
  feudal: "Feudal",
  castle: "Castle",
  imperial: "Imperial",
};

interface Row {
  t: number;
  [player: string]: number | null;
}

/** Align each player's samples onto one time axis. */
function toRows(players: PlayerAnalysis[]): Row[] {
  const stamps = new Set<number>();
  for (const p of players) for (const point of p.resource_curve) stamps.add(point.timestamp_ms);

  return [...stamps]
    .sort((a, b) => a - b)
    .map((t) => {
      const row: Row = { t };
      for (const p of players) {
        row[p.name] = p.resource_curve.find((point) => point.timestamp_ms === t)?.banked ?? null;
      }
      return row;
    });
}

export function ResourceCurveChart({ players }: { players: PlayerAnalysis[] }) {
  const rows = toRows(players);
  if (rows.length === 0) {
    return (
      <p className="text-sm text-ink-muted">
        This replay carries no resource telemetry.
      </p>
    );
  }

  // Age advances, drawn as reference lines so timings read against the curve.
  const ageMarks = players.flatMap((p, i) =>
    Object.entries(p.age_timings_ms).map(([age, ms]) => ({ age, ms, seriesIndex: i })),
  );

  return (
    <figure className="viz-root space-y-2">
      <figcaption className="text-sm text-ink-muted">
        Banked resources over time — food, wood, gold and stone combined. Resources
        sitting in the bank are resources not yet converted into army or economy.
      </figcaption>
      <div className="h-72 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={rows} margin={{ top: 8, right: 12, bottom: 4, left: 4 }}>
            <CartesianGrid stroke="var(--viz-grid)" strokeDasharray="2 4" vertical={false} />
            <XAxis
              dataKey="t"
              type="number"
              domain={["dataMin", "dataMax"]}
              tickFormatter={clock}
              stroke="var(--viz-axis)"
              tick={{ fill: "var(--viz-text-muted)", fontSize: 12 }}
              tickLine={false}
              minTickGap={48}
            />
            <YAxis
              stroke="var(--viz-axis)"
              tick={{ fill: "var(--viz-text-muted)", fontSize: 12 }}
              tickLine={false}
              width={48}
            />
            {ageMarks.map(({ age, ms, seriesIndex }) => (
              <ReferenceLine
                key={`${seriesIndex}-${age}`}
                x={ms}
                stroke={SERIES[seriesIndex % SERIES.length]}
                strokeDasharray="3 3"
                strokeOpacity={0.5}
                label={{
                  value: AGE_LABEL[age] ?? age,
                  position: "insideTop",
                  fill: "var(--viz-text-muted)",
                  fontSize: 11,
                }}
              />
            ))}
            <Tooltip
              labelFormatter={(t) => `${clock(Number(t))} game time`}
              formatter={(v, name) => [
                typeof v === "number" ? v.toLocaleString() : "—",
                String(name),
              ]}
              contentStyle={{
                background: "var(--viz-surface)",
                border: "1px solid var(--viz-grid)",
                borderRadius: 8,
                color: "var(--viz-text)",
                fontSize: 12,
              }}
            />
            <Legend
              wrapperStyle={{ fontSize: 12, color: "var(--viz-text-muted)" }}
              iconType="plainline"
            />
            {players.map((p, i) => (
              <Line
                key={p.name}
                type="monotone"
                dataKey={p.name}
                stroke={SERIES[i % SERIES.length]}
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4 }}
                connectNulls
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </figure>
  );
}

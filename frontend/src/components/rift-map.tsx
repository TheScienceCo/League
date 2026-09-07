"use client";

import { useMemo, useState } from "react";

import { zoneLabel } from "@/lib/format";

/**
 * Summoner's Rift rendered as inline SVG.
 *
 * Drawn rather than using a map image: the lanes, river and pits are the only
 * landmarks the analysis refers to, an SVG stays sharp at any size, and it
 * carries no third-party art. World coordinates run 0–15000 with y increasing
 * upward, so the whole scene is flipped once on the y axis rather than every
 * point being converted individually.
 */

const MAP_MAX = 15000;

const LANES: Array<[number, number][]> = [
  // Top
  [
    [1000, 4200], [1300, 10500], [2500, 12800], [5000, 13300], [11500, 13300], [13000, 12600],
  ],
  // Mid
  [
    [2200, 2200], [7000, 7000], [12800, 12800],
  ],
  // Bot
  [
    [4200, 1000], [10500, 1300], [12800, 2500], [13300, 5000], [13300, 11500], [12600, 13000],
  ],
];

const DRAGON: [number, number] = [9866, 4414];
const BARON: [number, number] = [5007, 10471];

function pathFrom(points: [number, number][]): string {
  return points.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x} ${y}`).join(" ");
}

export interface MapCell {
  cell_x: number;
  cell_y: number;
  /** The quantity that drives colour. */
  intensity: number;
  exposures?: number;
  deaths?: number;
  zone?: string | null;
  label?: string;
}

export interface MapMarker {
  x: number;
  y: number;
  label?: string;
}

/**
 * Sequential ramp for risk.
 *
 * Stops from the `magma` colormap. A rainbow hue rotation would look livelier
 * but is perceptually non-uniform — equal steps in the data do not read as equal
 * steps in colour, and mid-range values shout as loudly as extremes. Magma rises
 * monotonically in lightness, which keeps the ordering readable on the dark
 * ground and survives greyscale and the common forms of colour blindness.
 */
const RISK_RAMP: Array<[number, number, number]> = [
  [12, 14, 34],
  [59, 15, 112],
  [140, 41, 129],
  [222, 73, 104],
  [254, 159, 109],
  [252, 253, 191],
];

function riskColour(t: number): string {
  const clamped = Math.max(0, Math.min(1, t));
  const scaled = clamped * (RISK_RAMP.length - 1);
  const lower = Math.floor(scaled);
  const upper = Math.min(lower + 1, RISK_RAMP.length - 1);
  const frac = scaled - lower;
  const a = RISK_RAMP[lower] ?? RISK_RAMP[0]!;
  const b = RISK_RAMP[upper] ?? RISK_RAMP[RISK_RAMP.length - 1]!;
  const mix = (i: 0 | 1 | 2) => Math.round(a[i] + (b[i] - a[i]) * frac);
  return `rgb(${mix(0)} ${mix(1)} ${mix(2)})`;
}

export function RiftMap({
  cells = [],
  markers = [],
  gridSize = 32,
  maxIntensity,
  legendLabel = "Death risk",
  markerLabel = "Deaths",
  height = 460,
}: {
  cells?: MapCell[];
  markers?: MapMarker[];
  gridSize?: number;
  maxIntensity?: number;
  legendLabel?: string;
  markerLabel?: string;
  height?: number;
}) {
  const [hover, setHover] = useState<MapCell | null>(null);
  const span = MAP_MAX / gridSize;

  const scaleMax = useMemo(() => {
    if (maxIntensity !== undefined) return maxIntensity;
    if (cells.length === 0) return 1;
    // Scale to a high percentile rather than the maximum, so one freak cell does
    // not flatten the whole map into the bottom of the ramp.
    const sorted = [...cells].map((c) => c.intensity).sort((a, b) => a - b);
    const idx = Math.floor(sorted.length * 0.95);
    return sorted[Math.min(idx, sorted.length - 1)] ?? 1;
  }, [cells, maxIntensity]);

  return (
    <div className="relative">
      <svg
        viewBox={`0 0 ${MAP_MAX} ${MAP_MAX}`}
        style={{ height, width: "100%" }}
        role="img"
        aria-label="Summoner's Rift map with analysis overlay"
        className="rounded border border-surface-border bg-[#0b1016]"
      >
        {/* One flip so world coordinates (y up) can be used directly. */}
        <g transform={`translate(0, ${MAP_MAX}) scale(1, -1)`}>
          <rect x={0} y={0} width={MAP_MAX} height={MAP_MAX} fill="#0b1016" />

          {/* River band */}
          <path
            d={`M ${MAP_MAX} 0 L 0 ${MAP_MAX} L 0 ${MAP_MAX - 2600} L ${MAP_MAX - 2600} 0 Z`}
            fill="#12202c"
            opacity={0.55}
          />

          {LANES.map((lane, i) => (
            <path
              key={i}
              d={pathFrom(lane)}
              fill="none"
              stroke="#1f2a36"
              strokeWidth={2000}
              strokeLinecap="round"
              strokeLinejoin="round"
              opacity={0.75}
            />
          ))}

          {/* Bases */}
          <circle cx={1600} cy={1600} r={2400} fill="#153048" opacity={0.7} />
          <circle cx={13400} cy={13400} r={2400} fill="#40202a" opacity={0.7} />

          {/* Risk cells */}
          {cells.map((cell) => {
            const t = scaleMax > 0 ? cell.intensity / scaleMax : 0;
            return (
              <rect
                key={`${cell.cell_x}-${cell.cell_y}`}
                x={cell.cell_x * span}
                y={cell.cell_y * span}
                width={span}
                height={span}
                fill={riskColour(t)}
                opacity={0.35 + 0.5 * Math.min(1, t)}
                onMouseEnter={() => setHover(cell)}
                onMouseLeave={() => setHover(null)}
              />
            );
          })}

          {/* Objective pits */}
          <circle cx={DRAGON[0]} cy={DRAGON[1]} r={620} fill="none" stroke="#d29922" strokeWidth={110} />
          <circle cx={BARON[0]} cy={BARON[1]} r={620} fill="none" stroke="#8957e5" strokeWidth={110} />

          {markers.map((m, i) => (
            <g key={i}>
              <circle cx={m.x} cy={m.y} r={150} fill="#f85149" opacity={0.85} />
              <circle cx={m.x} cy={m.y} r={280} fill="none" stroke="#f85149" strokeWidth={45} opacity={0.4} />
            </g>
          ))}
        </g>

        {/* Labels are drawn outside the flip so text is not mirrored. */}
        <text x={DRAGON[0] - 900} y={MAP_MAX - DRAGON[1] - 800} fill="#d29922" fontSize={380}>
          Dragon
        </text>
        <text x={BARON[0] - 700} y={MAP_MAX - BARON[1] - 800} fill="#a371f7" fontSize={380}>
          Baron
        </text>
      </svg>

      <div className="mt-2 flex flex-wrap items-center gap-3 text-xs text-ink-muted">
        <span className="flex items-center gap-1.5">
          {legendLabel}
          <span className="inline-flex h-2 w-28 overflow-hidden rounded">
            {Array.from({ length: 14 }, (_, i) => (
              <span key={i} className="h-full flex-1" style={{ background: riskColour(i / 13) }} />
            ))}
          </span>
          <span className="text-ink-faint">low → high</span>
        </span>
        {markers.length > 0 && (
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-2 w-2 rounded-full bg-bad" />
            {markerLabel} ({markers.length})
          </span>
        )}
      </div>

      {hover && (
        <div className="pointer-events-none absolute left-2 top-2 rounded border border-surface-border bg-surface-overlay px-2.5 py-1.5 text-xs shadow">
          <div className="font-medium">
            {hover.zone ? zoneLabel(hover.zone) : `Cell ${hover.cell_x}, ${hover.cell_y}`}
          </div>
          <div className="text-ink-muted">
            {hover.label ?? `Intensity ${hover.intensity.toFixed(3)}`}
          </div>
          {hover.exposures !== undefined && (
            <div className="text-ink-faint">
              {hover.deaths ?? 0} deaths / {hover.exposures.toLocaleString()} observations
            </div>
          )}
        </div>
      )}
    </div>
  );
}

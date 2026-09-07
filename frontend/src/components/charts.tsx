"use client";

import {
  Area,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { TimelinePoint } from "@/lib/types";

/**
 * Chart tokens.
 *
 * One accent for the subject, one neutral for the comparison, and a
 * good/bad pair reserved for signed quantities. Keeping series colours to this
 * small set is what makes the pages read as one system rather than a gallery of
 * unrelated charts.
 *
 * Entry animation is disabled everywhere: on a dashboard this dense it delays
 * first paint for no benefit, and it makes screenshots and visual checks
 * unreliable.
 */
const COLORS = {
  primary: "#4c9aff",
  secondary: "#9aa7b4",
  good: "#3fb950",
  bad: "#f85149",
  grid: "#262d38",
  axis: "#6b7785",
};

const axisProps = {
  stroke: COLORS.axis,
  tick: { fill: COLORS.axis, fontSize: 11 },
  tickLine: false,
  axisLine: { stroke: COLORS.grid },
};

const tooltipStyle = {
  contentStyle: {
    background: "#1c232c",
    border: "1px solid #262d38",
    borderRadius: 6,
    fontSize: 12,
  },
  labelStyle: { color: "#9aa7b4" },
};

export function GoldXpChart({ data }: { data: TimelinePoint[] }) {
  return (
    <ResponsiveContainer width="100%" height={240}>
      <LineChart data={data} margin={{ top: 5, right: 8, left: -12, bottom: 0 }}>
        <CartesianGrid stroke={COLORS.grid} strokeDasharray="3 3" vertical={false} />
        <XAxis dataKey="minute" {...axisProps} unit="m" />
        <YAxis {...axisProps} width={54} />
        <Tooltip {...tooltipStyle} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Line
          type="monotone"
          dataKey="gold"
          name="Gold"
          stroke={COLORS.primary}
          strokeWidth={2}
          dot={false}
          isAnimationActive={false}
        />
        <Line
          type="monotone"
          dataKey="xp"
          name="XP"
          stroke={COLORS.secondary}
          strokeWidth={1.5}
          strokeDasharray="4 3"
          dot={false}
          isAnimationActive={false}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}

/** Signed differential against the lane opponent; zero line is the story. */
export function DiffChart({
  data,
  dataKey,
  label,
}: {
  data: TimelinePoint[];
  dataKey: "gold_diff" | "xp_diff" | "cs_diff" | "team_gold_diff";
  label: string;
}) {
  const shaped = data.map((d) => ({
    minute: d.minute,
    positive: (d[dataKey] ?? 0) > 0 ? d[dataKey] : 0,
    negative: (d[dataKey] ?? 0) <= 0 ? d[dataKey] : 0,
    value: d[dataKey],
  }));
  return (
    <ResponsiveContainer width="100%" height={200}>
      <ComposedChart data={shaped} margin={{ top: 5, right: 8, left: -12, bottom: 0 }}>
        <CartesianGrid stroke={COLORS.grid} strokeDasharray="3 3" vertical={false} />
        <XAxis dataKey="minute" {...axisProps} unit="m" />
        <YAxis {...axisProps} width={54} />
        <Tooltip {...tooltipStyle} formatter={(v: number) => [Math.round(v), label]} />
        <ReferenceLine y={0} stroke={COLORS.axis} />
        <Area
          type="monotone"
          dataKey="positive"
          stroke={COLORS.good}
          fill={COLORS.good}
          fillOpacity={0.18}
          isAnimationActive={false}
        />
        <Area
          type="monotone"
          dataKey="negative"
          stroke={COLORS.bad}
          fill={COLORS.bad}
          fillOpacity={0.18}
          isAnimationActive={false}
        />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

/**
 * Value formats a bar chart can render.
 *
 * A string rather than a callback on purpose: these charts are client
 * components rendered from server components, and functions cannot cross that
 * boundary. Naming the format keeps the prop serializable.
 */
export type BarFormat = "decimal" | "percent" | "sigma";

function formatBarValue(value: number, format: BarFormat): string {
  if (format === "percent") return `${(value * 100).toFixed(1)}%`;
  if (format === "sigma") return `${value >= 0 ? "+" : ""}${value.toFixed(2)}σ`;
  return value.toFixed(3);
}

export function HorizontalBars({
  data,
  valueKey = "value",
  labelKey = "label",
  height = 280,
  format = "decimal",
  diverging = false,
}: {
  data: Array<Record<string, string | number | null>>;
  valueKey?: string;
  labelKey?: string;
  height?: number;
  format?: BarFormat;
  diverging?: boolean;
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} layout="vertical" margin={{ top: 4, right: 16, left: 8, bottom: 4 }}>
        <CartesianGrid stroke={COLORS.grid} strokeDasharray="3 3" horizontal={false} />
        <XAxis type="number" {...axisProps} />
        <YAxis
          type="category"
          dataKey={labelKey}
          {...axisProps}
          width={190}
          tick={{ fill: COLORS.axis, fontSize: 11 }}
        />
        <Tooltip {...tooltipStyle} formatter={(v: number) => [formatBarValue(v, format), ""]} />
        {diverging && <ReferenceLine x={0} stroke={COLORS.axis} />}
        <Bar dataKey={valueKey} radius={[0, 3, 3, 0]} isAnimationActive={false}>
          {data.map((row, i) => {
            const v = Number(row[valueKey] ?? 0);
            return (
              <Cell
                key={i}
                fill={diverging ? (v >= 0 ? COLORS.bad : COLORS.good) : COLORS.primary}
              />
            );
          })}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

export function TrendChart({
  data,
  series,
}: {
  data: Array<Record<string, number | string | boolean | null>>;
  series: Array<{ key: string; label: string }>;
}) {
  return (
    <ResponsiveContainer width="100%" height={220}>
      <LineChart data={data} margin={{ top: 5, right: 8, left: -12, bottom: 0 }}>
        <CartesianGrid stroke={COLORS.grid} strokeDasharray="3 3" vertical={false} />
        <XAxis dataKey="index" {...axisProps} />
        <YAxis {...axisProps} width={48} />
        <Tooltip {...tooltipStyle} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        {series.map((s, i) => (
          <Line
            key={s.key}
            type="monotone"
            dataKey={s.key}
            name={s.label}
            stroke={i === 0 ? COLORS.primary : COLORS.secondary}
            strokeWidth={i === 0 ? 2 : 1.5}
            dot={false}
            connectNulls
            isAnimationActive={false}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}

export function TierMeansChart({
  data,
}: {
  data: Array<{ tier: string; value: number | null }>;
}) {
  return (
    <ResponsiveContainer width="100%" height={180}>
      <BarChart data={data} margin={{ top: 4, right: 8, left: -12, bottom: 0 }}>
        <CartesianGrid stroke={COLORS.grid} strokeDasharray="3 3" vertical={false} />
        <XAxis dataKey="tier" {...axisProps} interval={0} angle={-18} textAnchor="end" height={54} />
        <YAxis {...axisProps} width={54} />
        <Tooltip {...tooltipStyle} />
        <Bar dataKey="value" fill={COLORS.primary} radius={[3, 3, 0, 0]} isAnimationActive={false} />
      </BarChart>
    </ResponsiveContainer>
  );
}

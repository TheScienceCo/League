/** `754000` -> `"12:34"`. */
export function clock(ms: number): string {
  const total = Math.round(ms / 1000);
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

/** Signed clock for deltas: `-92000` -> `"-1:32"`. */
export function signedClock(ms: number): string {
  return (ms < 0 ? "-" : "+") + clock(Math.abs(ms));
}

/** Render a metric's value for display, honouring its unit. */
export function metricValue(value: number | null, unit: string): string {
  if (value === null) return "—";
  if (unit === "ms") return clock(value);
  return value.toLocaleString();
}

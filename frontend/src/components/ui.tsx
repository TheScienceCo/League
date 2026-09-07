import Link from "next/link";
import type { ReactNode } from "react";

export function Card({
  title,
  subtitle,
  action,
  children,
  className = "",
}: {
  title?: ReactNode;
  subtitle?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`card ${className}`}>
      {(title || action) && (
        <header className="flex items-start justify-between gap-3 border-b border-surface-border px-4 py-3 sm:px-5">
          <div>
            {title && <h2 className="text-sm font-semibold">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-xs text-ink-muted">{subtitle}</p>}
          </div>
          {action}
        </header>
      )}
      <div className="card-pad">{children}</div>
    </section>
  );
}

export function Stat({
  label,
  value,
  hint,
  tone = "",
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  tone?: string;
}) {
  return (
    <div>
      <div className="label">{label}</div>
      <div className={`stat mt-1 text-xl ${tone}`}>{value}</div>
      {hint && <div className="mt-0.5 text-xs text-ink-faint">{hint}</div>}
    </div>
  );
}

export function Badge({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "neutral" | "good" | "bad" | "warn" | "accent";
}) {
  const tones: Record<string, string> = {
    neutral: "bg-surface-overlay text-ink-muted",
    good: "bg-good/15 text-good",
    bad: "bg-bad/15 text-bad",
    warn: "bg-warn/15 text-warn",
    accent: "bg-accent/15 text-accent",
  };
  return (
    <span
      className={`inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium ${tones[tone]}`}
    >
      {children}
    </span>
  );
}

/**
 * A percentile rendered as a bar. `value` is already oriented so that higher is
 * better, which keeps the colour meaning consistent across metrics where a low
 * raw number is the good outcome (deaths, risk).
 */
export function PercentileBar({ value }: { value: number | null }) {
  if (value === null) {
    return <div className="h-1.5 w-full rounded bg-surface-overlay" />;
  }
  const pct = Math.max(0, Math.min(100, value));
  const colour = pct >= 75 ? "bg-good" : pct >= 45 ? "bg-accent" : pct >= 25 ? "bg-warn" : "bg-bad";
  return (
    <div
      className="h-1.5 w-full overflow-hidden rounded bg-surface-overlay"
      role="img"
      aria-label={`${Math.round(pct)}th percentile`}
    >
      <div className={`h-full rounded ${colour}`} style={{ width: `${pct}%` }} />
    </div>
  );
}

export function EmptyState({
  title,
  children,
  action,
}: {
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="rounded-lg border border-dashed border-surface-border px-6 py-10 text-center">
      <p className="text-sm font-medium">{title}</p>
      {children && <p className="mx-auto mt-2 max-w-md text-sm text-ink-muted">{children}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function Disclaimer({ children }: { children: ReactNode }) {
  return (
    <p className="mt-3 rounded border border-surface-border bg-surface-overlay/50 px-3 py-2 text-xs leading-relaxed text-ink-muted">
      {children}
    </p>
  );
}

export function PlayerTabs({
  platform,
  riotId,
  active,
}: {
  platform: string;
  riotId: string;
  active: string;
}) {
  const base = `/player/${platform}/${encodeURIComponent(riotId)}`;
  const tabs = [
    { key: "overview", href: base, label: "Overview" },
    { key: "matches", href: `${base}/matches`, label: "Matches" },
    { key: "advanced", href: `${base}/advanced`, label: "Advanced stats" },
    { key: "map", href: `${base}/map`, label: "Map & risk" },
    { key: "skill-gap", href: `${base}/skill-gap`, label: "Skill gap" },
    { key: "compare", href: `${base}/compare`, label: "Compare" },
  ];
  return (
    <nav className="scroll-x -mx-4 mb-5 border-b border-surface-border px-4">
      <ul className="flex min-w-max gap-1 text-sm">
        {tabs.map((tab) => (
          <li key={tab.key}>
            <Link
              href={tab.href}
              className={`inline-block border-b-2 px-3 py-2 ${
                active === tab.key
                  ? "border-accent text-ink"
                  : "border-transparent text-ink-muted hover:text-ink"
              }`}
            >
              {tab.label}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}

export function ErrorNotice({ title, message }: { title: string; message: string }) {
  return (
    <div className="rounded-lg border border-bad/40 bg-bad/10 px-4 py-3">
      <p className="text-sm font-medium text-bad">{title}</p>
      <p className="mt-1 text-sm text-ink-muted">{message}</p>
    </div>
  );
}

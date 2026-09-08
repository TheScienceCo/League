import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "AoE2 Analytics — Replay analysis & coaching",
    template: "%s · AoE2 Analytics",
  },
  description:
    "Post-game Age of Empires II analytics: economy, military, scouting metrics, peer comparison, and coaching insights from replay analysis.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen">
        <header className="border-b border-surface-border bg-surface-raised/60 backdrop-blur">
          <div className="mx-auto flex max-w-7xl items-center gap-6 px-4 py-3">
            <Link href="/" className="flex items-center gap-2 font-semibold">
              <span
                aria-hidden
                className="inline-block h-5 w-5 rounded bg-gradient-to-br from-accent to-accent-soft"
              />
              AoE2 Analytics
            </Link>
            <nav className="flex items-center gap-4 text-sm text-ink-muted">
              <Link href="/upload" className="hover:text-ink">
                Upload Replay
              </Link>
              <Link href="/methodology" className="hover:text-ink">
                Methodology
              </Link>
              <Link href="https://github.com/thescienceco/league" className="hover:text-ink">
                GitHub
              </Link>
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-7xl px-4 py-6">{children}</main>
        <footer className="mx-auto max-w-7xl px-4 pb-10 pt-4 text-xs text-ink-faint">
          <p>
            Replay analysis is retrospective and based on match data that players can already access.
            Model-derived figures (ML estimates) describe association, not causation.
            Not endorsed by or affiliated with Microsoft or Relic Entertainment.
          </p>
        </footer>
      </body>
    </html>
  );
}

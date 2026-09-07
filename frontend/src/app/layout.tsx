import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "Rift Lab — League analytics & coaching",
    template: "%s · Rift Lab",
  },
  description:
    "Post-game League of Legends analytics: derived metrics, peer cohorts, map risk modelling and skill-gap analysis.",
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
              Rift Lab
            </Link>
            <nav className="flex items-center gap-4 text-sm text-ink-muted">
              <Link href="/insights" className="hover:text-ink">
                Rank separation
              </Link>
              <Link href="/map" className="hover:text-ink">
                Map risk
              </Link>
              <Link href="/methodology" className="hover:text-ink">
                Methodology
              </Link>
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-7xl px-4 py-6">{children}</main>
        <footer className="mx-auto max-w-7xl px-4 pb-10 pt-4 text-xs text-ink-faint">
          <p>
            Post-game analysis of publicly available match history. Model-derived
            figures are estimates describing association, not causation. Not
            endorsed by or affiliated with Riot Games.
          </p>
        </footer>
      </body>
    </html>
  );
}

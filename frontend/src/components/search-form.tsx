"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { PLATFORMS } from "@/lib/format";

export function SearchForm({
  defaultPlatform = "na1",
  autoFocus = false,
}: {
  defaultPlatform?: string;
  autoFocus?: boolean;
}) {
  const router = useRouter();
  const [riotId, setRiotId] = useState("");
  const [platform, setPlatform] = useState(defaultPlatform);
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  function submit(event: React.FormEvent) {
    event.preventDefault();
    const trimmed = riotId.trim();
    if (!trimmed.includes("#")) {
      setError("Enter a Riot ID in the form Name#TAG");
      return;
    }
    setError(null);
    startTransition(() => {
      router.push(`/player/${platform}/${encodeURIComponent(trimmed)}`);
    });
  }

  return (
    <form onSubmit={submit} className="w-full">
      <div className="flex flex-col gap-2 sm:flex-row">
        <input
          autoFocus={autoFocus}
          value={riotId}
          onChange={(e) => setRiotId(e.target.value)}
          placeholder="Name#TAG"
          aria-label="Riot ID"
          className="flex-1 rounded border border-surface-border bg-surface px-3 py-2 text-sm outline-none placeholder:text-ink-faint focus:border-accent"
        />
        <select
          value={platform}
          onChange={(e) => setPlatform(e.target.value)}
          aria-label="Platform"
          className="rounded border border-surface-border bg-surface px-3 py-2 text-sm outline-none focus:border-accent"
        >
          {PLATFORMS.map((p) => (
            <option key={p} value={p}>
              {p.toUpperCase()}
            </option>
          ))}
        </select>
        <button
          type="submit"
          disabled={pending}
          className="rounded bg-accent px-4 py-2 text-sm font-medium text-surface disabled:opacity-60"
        >
          {pending ? "Loading…" : "Analyse"}
        </button>
      </div>
      {error && <p className="mt-2 text-xs text-bad">{error}</p>}
    </form>
  );
}

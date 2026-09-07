"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { api } from "@/lib/api";
import type { IngestJob } from "@/lib/types";

/**
 * Starts an ingestion job and polls it to completion.
 *
 * Ingestion is asynchronous on the backend (it is rate-limited upstream and can
 * take a while), so the UI's job is to start it, show honest progress, and
 * refresh the page's server components when it finishes.
 */
export function IngestButton({
  riotId,
  platform,
  count = 20,
  label = "Ingest recent matches",
}: {
  riotId: string;
  platform: string;
  count?: number;
  label?: string;
}) {
  const router = useRouter();
  const [job, setJob] = useState<IngestJob | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const cancelled = useRef(false);

  // A component unmounted mid-poll must stop calling setState.
  useEffect(() => {
    cancelled.current = false;
    return () => {
      cancelled.current = true;
    };
  }, []);

  const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

  /**
   * Poll the job to completion.
   *
   * A loop rather than a self-scheduling callback: the recursive form has to
   * reference itself before it is declared, which is both a lint error and a
   * genuine footgun when the closure is recreated.
   */
  async function pollToCompletion(jobId: string) {
    await sleep(800);
    while (!cancelled.current) {
      const next = await api.job(jobId);
      if (cancelled.current) return;
      setJob(next);
      if (next.status !== "PENDING" && next.status !== "RUNNING") {
        if (next.error) setError(next.error);
        return;
      }
      await sleep(1200);
    }
  }

  async function start() {
    setError(null);
    setRunning(true);
    try {
      const started = await api.startIngest({ riot_id: riotId, platform, count });
      setJob(started);
      await pollToCompletion(started.id);
      if (!cancelled.current) router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start ingestion");
    } finally {
      if (!cancelled.current) setRunning(false);
    }
  }

  const progress = job ? Math.round(job.progress * 100) : 0;

  return (
    <div className="flex flex-col items-end gap-1">
      <button
        onClick={start}
        disabled={running}
        className="rounded border border-surface-border bg-surface-overlay px-3 py-1.5 text-xs font-medium hover:border-accent disabled:opacity-60"
      >
        {running ? `Ingesting… ${progress}%` : label}
      </button>
      {job && !running && !error && (
        <span className="text-xs text-ink-faint">
          {job.matches_ingested} new, {job.matches_skipped} already stored
        </span>
      )}
      {error && <span className="max-w-xs text-right text-xs text-bad">{error}</span>}
    </div>
  );
}

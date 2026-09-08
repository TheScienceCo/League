"use client";

import { useState } from "react";
import Link from "next/link";

export default function UploadPage() {
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [uploadId, setUploadId] = useState<number | null>(null);

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const files = e.dataTransfer.files;
    if (files.length > 0) {
      const f = files[0];
      if (f.name.endsWith(".aoe2record") || f.name.endsWith(".mgz")) {
        setFile(f);
        setError(null);
      } else {
        setError("Please upload a .aoe2record or .mgz file");
      }
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      setFile(files[0]);
      setError(null);
    }
  };

  const handleUpload = async () => {
    if (!file) {
      setError("No file selected");
      return;
    }

    setUploading(true);
    setProgress(0);
    setError(null);

    try {
      // Simulate upload progress
      const interval = setInterval(() => {
        setProgress((p) => (p < 90 ? p + Math.random() * 30 : p));
      }, 200);

      const formData = new FormData();
      formData.append("file", file);

      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/v1/aoe2/replays/upload`,
        {
          method: "POST",
          body: formData,
        }
      );

      clearInterval(interval);
      setProgress(100);

      if (!response.ok) {
        throw new Error("Upload failed");
      }

      const data = await response.json();
      setUploadId(data.replay_id);
      setFile(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="space-y-8 py-8">
      <div className="space-y-2">
        <h1 className="text-3xl font-bold">Upload Replay</h1>
        <p className="text-ink-muted">
          Select an Age of Empires II replay file (.aoe2record) to analyze
        </p>
      </div>

      {uploadId ? (
        // Success state
        <div className="space-y-4 rounded-lg border border-green-200 bg-green-50 p-6 dark:border-green-800 dark:bg-green-900/20">
          <h2 className="font-semibold text-green-900 dark:text-green-200">
            ✓ Upload successful!
          </h2>
          <p className="text-sm text-green-800 dark:text-green-300">
            Your replay has been queued for analysis. Processing typically takes 30-60 seconds.
          </p>
          <div className="flex gap-4">
            <Link
              href={`/aoe2/replays/${uploadId}/status`}
              className="inline-block rounded-lg bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700 transition"
            >
              Check Status
            </Link>
            <button
              onClick={() => {
                setUploadId(null);
                setFile(null);
                setProgress(0);
              }}
              className="inline-block rounded-lg border border-green-600 px-4 py-2 text-sm font-medium text-green-600 hover:bg-green-50 transition dark:text-green-400 dark:hover:bg-green-900/20"
            >
              Upload Another
            </button>
          </div>
        </div>
      ) : (
        // Upload form
        <div className="space-y-6">
          {/* Drop zone */}
          <div
            onDrop={handleDrop}
            onDragOver={(e) => e.preventDefault()}
            className="space-y-4 rounded-lg border-2 border-dashed border-surface-border bg-surface-raised/50 p-8 text-center transition hover:border-accent hover:bg-surface-raised"
          >
            <div className="space-y-2">
              <p className="text-lg font-medium">Drag and drop your replay file</p>
              <p className="text-sm text-ink-muted">
                Supported formats: .aoe2record, .mgz (max 100 MB)
              </p>
            </div>

            <div className="flex items-center justify-center gap-2 text-sm text-ink-muted">
              <span>Or</span>
              <label className="cursor-pointer">
                <span className="text-accent hover:underline">choose a file</span>
                <input
                  type="file"
                  accept=".aoe2record,.mgz"
                  onChange={handleFileSelect}
                  className="hidden"
                />
              </label>
            </div>
          </div>

          {/* Selected file */}
          {file && (
            <div className="rounded-lg border border-surface-border bg-surface-raised p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="font-medium">{file.name}</p>
                  <p className="text-sm text-ink-muted">
                    {(file.size / 1024 / 1024).toFixed(2)} MB
                  </p>
                </div>
                <button
                  onClick={() => setFile(null)}
                  className="text-sm text-ink-muted hover:text-ink"
                >
                  Remove
                </button>
              </div>

              {uploading && (
                <div className="mt-4 space-y-2">
                  <div className="flex items-center justify-between text-xs text-ink-muted">
                    <span>Uploading...</span>
                    <span>{Math.round(progress)}%</span>
                  </div>
                  <div className="h-2 rounded-full bg-surface-border overflow-hidden">
                    <div
                      className="h-full bg-accent transition-all"
                      style={{ width: `${progress}%` }}
                    />
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Error message */}
          {error && (
            <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-900 dark:border-red-800 dark:bg-red-900/20 dark:text-red-200">
              {error}
            </div>
          )}

          {/* Upload button */}
          <button
            onClick={handleUpload}
            disabled={!file || uploading}
            className="w-full rounded-lg bg-accent px-6 py-3 font-medium text-white hover:bg-accent-dark disabled:bg-surface-border disabled:text-ink-muted disabled:cursor-not-allowed transition"
          >
            {uploading ? "Uploading..." : "Upload and Analyze"}
          </button>

          {/* Info */}
          <div className="space-y-4 rounded-lg border border-surface-border/50 bg-surface-raised/50 p-4 text-sm text-ink-muted">
            <h3 className="font-semibold text-ink">What happens next?</h3>
            <ol className="space-y-2 list-decimal list-inside">
              <li>Your replay file is parsed to extract game events</li>
              <li>Game state is reconstructed from the event stream</li>
              <li>All metrics are calculated (economy, military, strategy, etc.)</li>
              <li>Results are compared to peer cohorts by Elo and civilization</li>
              <li>A coaching report is generated with insights</li>
            </ol>
            <p className="pt-2 border-t border-surface-border">
              Processing typically takes 30-60 seconds. You can check status anytime.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

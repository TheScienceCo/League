"use client";

import { ErrorNotice } from "@/components/ui";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="space-y-3">
      <ErrorNotice title="Something went wrong" message={error.message} />
      <button onClick={reset} className="link text-sm">
        Try again
      </button>
    </div>
  );
}

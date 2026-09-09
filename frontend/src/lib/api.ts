import type { MatchAnalysis } from "@/lib/types";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

/** Upload a replay and get its analysis. Throws `ApiError` with the server's explanation. */
export async function uploadReplay(file: File): Promise<MatchAnalysis> {
  const body = new FormData();
  body.append("file", file);

  let response: Response;
  try {
    response = await fetch(`${BASE}/api/v1/replays`, { method: "POST", body });
  } catch {
    throw new ApiError(
      `Could not reach the API at ${BASE}. Is it running? (\`docker compose up\`)`,
      0,
    );
  }

  if (!response.ok) {
    // The API explains parse failures in `detail`; surface that rather than a status code.
    const detail = await response
      .json()
      .then((b) => b?.detail)
      .catch(() => null);
    throw new ApiError(detail ?? `Upload failed (HTTP ${response.status}).`, response.status);
  }
  return response.json();
}

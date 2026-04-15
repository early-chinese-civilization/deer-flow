import { getBackendBaseURL } from "../config";

import type { ThreadRecord } from "./types";

async function readErrorDetail(
  response: Response,
  fallback: string,
): Promise<string> {
  const error = await response.json().catch(() => ({ detail: fallback }));
  return error.detail ?? fallback;
}

export async function ensureThread(threadId: string): Promise<ThreadRecord> {
  const response = await fetch(`${getBackendBaseURL()}/api/threads`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    credentials: "include",
    body: JSON.stringify({
      thread_id: threadId,
    }),
  });

  if (!response.ok) {
    throw new Error(await readErrorDetail(response, "Failed to ensure thread"));
  }

  return response.json();
}

export async function getThread(threadId: string): Promise<ThreadRecord> {
  const response = await fetch(
    `${getBackendBaseURL()}/api/threads/${encodeURIComponent(threadId)}`,
    {
      credentials: "include",
    },
  );

  if (!response.ok) {
    throw new Error(await readErrorDetail(response, "Failed to load thread"));
  }

  return response.json();
}

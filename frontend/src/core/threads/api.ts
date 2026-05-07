import { getBackendBaseURL } from "../config";

import { throwThreadApiError } from "./api-error";
import type { ThreadRecord } from "./types";

export { isThreadApiError } from "./api-error";

export async function ensureThread(
  threadId: string,
  options?: { workspaceId?: string | null },
): Promise<ThreadRecord> {
  const response = await fetch(`${getBackendBaseURL()}/api/threads`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    credentials: "include",
    body: JSON.stringify({
      thread_id: threadId,
      workspace_id: options?.workspaceId ?? undefined,
    }),
  });

  if (!response.ok) {
    return throwThreadApiError(response, "Failed to ensure thread");
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
    return throwThreadApiError(response, "Failed to load thread");
  }

  return response.json();
}

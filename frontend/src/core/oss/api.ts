import { getBackendBaseURL } from "../config/index.ts";

function buildDownloadUrlUrl(workspaceId: string, objectKey: string): string {
  const query = new URLSearchParams({ object_key: objectKey }).toString();
  return `${getBackendBaseURL()}/api/workspaces/${encodeURIComponent(workspaceId)}/uploads/download-url?${query}`;
}

async function readErrorDetail(
  response: Response,
  fallback: string,
): Promise<string> {
  const error = await response.json().catch(() => ({ detail: fallback }));
  return error.detail ?? fallback;
}

export interface WorkspaceDownloadUrlResponse {
  download_url: string;
  oss_uri: string;
}

export async function resolveWorkspaceDownloadUrl(
  workspaceId: string,
  objectKey: string,
): Promise<WorkspaceDownloadUrlResponse> {
  const response = await fetch(buildDownloadUrlUrl(workspaceId, objectKey), {
    credentials: "include",
  });

  if (!response.ok) {
    throw new Error(
      await readErrorDetail(response, "Failed to get download URL"),
    );
  }

  return response.json();
}

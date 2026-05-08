import { withBasePath } from "../auth/base-path";

function getBaseOrigin(): string {
  if (typeof window !== "undefined") {
    return window.location.origin;
  }

  return "http://localhost:2026";
}

function getBackendBaseURL(): string {
  const backendBaseURL = process.env.NEXT_PUBLIC_BACKEND_BASE_URL;

  if (backendBaseURL) {
    return new URL(backendBaseURL, getBaseOrigin()).toString().replace(/\/+$/, "");
  }

  return "";
}

function buildDownloadUrlUrl(workspaceId: string, objectKey: string): string {
  const query = new URLSearchParams({ object_key: objectKey }).toString();
  const path = `/api/workspaces/${encodeURIComponent(workspaceId)}/uploads/download-url?${query}`;
  const backendBaseURL = getBackendBaseURL();
  return backendBaseURL ? `${backendBaseURL}${path}` : withBasePath(path);
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

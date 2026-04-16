/**
 * API functions for file uploads
 */

import { getBackendBaseURL } from "../config";

export interface UploadedFileInfo {
  filename: string;
  size: number;
  path: string;
  virtual_path: string;
  artifact_url: string | null;
  object_key: string;
  signed_url?: string | null;
  extension?: string | null;
  modified?: number;
  markdown_file?: string | null;
  markdown_path?: string | null;
  markdown_virtual_path?: string | null;
  markdown_artifact_url?: string | null;
  markdown_object_key?: string | null;
  markdown_signed_url?: string | null;
}

export interface FileTreeNode {
  type: "file" | "directory";
  name: string;
  path: string;
  size?: number;
  modified?: number;
  children?: FileTreeNode[];
  // File-specific fields
  filename?: string;
  virtual_path?: string;
  artifact_url?: string | null;
  object_key?: string;
  signed_url?: string | null;
  extension?: string | null;
  markdown_file?: string | null;
  markdown_path?: string | null;
  markdown_virtual_path?: string | null;
  markdown_artifact_url?: string | null;
  markdown_object_key?: string | null;
  markdown_signed_url?: string | null;
}

export interface UploadResponse {
  success: boolean;
  files: UploadedFileInfo[];
  message: string;
}

export interface ListFilesResponse {
  root_label: string;
  root_path: string;
  files: UploadedFileInfo[];
  tree: FileTreeNode[];
  count: number;
}

export interface DeleteUploadedFileInput {
  filename: string;
  object_key: string;
}

type UploadRequestOptions = {
  threadId?: string;
};

async function readErrorDetail(
  response: Response,
  fallback: string,
): Promise<string> {
  const error = await response.json().catch(() => ({ detail: fallback }));
  return error.detail ?? fallback;
}

function buildUploadsUrl(
  workspaceId: string,
  suffix = "",
  options?: UploadRequestOptions,
): string {
  const baseUrl = `${getBackendBaseURL()}/api/workspaces/${encodeURIComponent(workspaceId)}/uploads${suffix}`;
  if (!options?.threadId) {
    return baseUrl;
  }

  const query = new URLSearchParams({
    thread_id: options.threadId,
  });
  return `${baseUrl}?${query.toString()}`;
}

/**
 * Upload files to a workspace
 */
export async function uploadFiles(
  workspaceId: string,
  files: File[],
  options?: UploadRequestOptions,
): Promise<UploadResponse> {
  const formData = new FormData();

  files.forEach((file) => {
    formData.append("files", file);
  });

  const response = await fetch(buildUploadsUrl(workspaceId, "", options), {
    method: "POST",
    body: formData,
    credentials: "include",
  });

  if (!response.ok) {
    throw new Error(await readErrorDetail(response, "Upload failed"));
  }

  return response.json();
}

/**
 * List all uploaded files for a workspace
 */
export async function listUploadedFiles(
  workspaceId: string,
  options?: UploadRequestOptions,
): Promise<ListFilesResponse> {
  const response = await fetch(buildUploadsUrl(workspaceId, "/list", options), {
    credentials: "include",
  });

  if (!response.ok) {
    throw new Error(
      await readErrorDetail(response, "Failed to list uploaded files"),
    );
  }

  return response.json();
}

/**
 * Delete an uploaded file
 */
export async function deleteUploadedFile(
  workspaceId: string,
  file: DeleteUploadedFileInput,
  options?: UploadRequestOptions,
): Promise<{ success: boolean; message: string }> {
  const response = await fetch(buildUploadsUrl(workspaceId, "", options), {
    method: "DELETE",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(file),
    credentials: "include",
  });

  if (!response.ok) {
    throw new Error(await readErrorDetail(response, "Failed to delete file"));
  }

  return response.json();
}

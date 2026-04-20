/**
 * API functions for file uploads
 */

import { getBackendBaseURL } from "../config";

export interface UploadedFileInfo {
  filename: string;
  size: number;
  path: string;
  virtual_path: string;
  relative_path: string;
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

function downloadBlobAsFile(blob: Blob, filename: string): void {
  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(objectUrl);
}

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
): string {
  return `${getBackendBaseURL()}/api/workspaces/${encodeURIComponent(workspaceId)}/uploads${suffix}`;
}

/**
 * Upload files to a workspace
 */
export async function uploadFiles(
  workspaceId: string,
  files: File[],
): Promise<UploadResponse> {
  const formData = new FormData();

  files.forEach((file) => {
    formData.append("files", file);
  });

  const response = await fetch(buildUploadsUrl(workspaceId, ""), {
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
): Promise<ListFilesResponse> {
  const response = await fetch(buildUploadsUrl(workspaceId, "/list"), {
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
): Promise<{ success: boolean; message: string }> {
  const response = await fetch(buildUploadsUrl(workspaceId, ""), {
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

/**
 * Download a workspace file without navigating away from the current page
 */
export async function downloadUploadedFile(
  url: string,
  filename: string,
): Promise<void> {
  const response = await fetch(url, {
    credentials: "include",
  });

  if (!response.ok) {
    throw new Error(await readErrorDetail(response, "Failed to download file"));
  }

  const blob = await response.blob();
  downloadBlobAsFile(blob, filename);
}

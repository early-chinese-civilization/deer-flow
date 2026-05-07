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

export interface UploadPrepareRequest {
  filename: string;
  content_type?: string | null;
  size?: number | null;
}

export interface UploadPrepareResponse {
  mode: "direct" | "multipart";
  method: "PUT" | null;
  upload_url: string | null;
  upload_headers: Record<string, string>;
  file: UploadedFileInfo;
}

export interface UploadFinalizeRequest {
  filename: string;
  object_key: string;
  size?: number | null;
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

function buildUploadsUrl(workspaceId: string, suffix = ""): string {
  return `${getBackendBaseURL()}/api/workspaces/${encodeURIComponent(workspaceId)}/uploads${suffix}`;
}

/**
 * 直接上传文件到 OSS（使用预签名 URL）
 * @param prepare - prepare 接口返回的预签名信息
 * @param file - 要上传的文件
 */
async function uploadDirectFile(
  prepare: UploadPrepareResponse,
  file: File,
): Promise<void> {
  if (!prepare.upload_url || !prepare.method) {
    throw new Error("Upload target is not ready for direct upload.");
  }

  const response = await fetch(prepare.upload_url, {
    method: prepare.method,
    headers: prepare.upload_headers,
    body: file,
  });

  if (!response.ok) {
    throw new Error("Direct upload failed");
  }
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
 * 准备上传：获取预签名 URL 和处理文件名冲突
 * @param workspaceId - workspace ID
 * @param payload - 文件信息（文件名、类型、大小）
 * @returns 预签名 URL 和文件元数据
 */
export async function prepareUpload(
  workspaceId: string,
  payload: UploadPrepareRequest,
): Promise<UploadPrepareResponse> {
  const response = await fetch(buildUploadsUrl(workspaceId, "/prepare"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
    credentials: "include",
  });

  if (!response.ok) {
    throw new Error(
      await readErrorDetail(response, "Failed to prepare upload"),
    );
  }

  return response.json();
}

/**
 * 确认上传完成：校验文件存在并返回元数据
 * @param workspaceId - workspace ID
 * @param payload - 文件信息（文件名、object key、大小）
 * @returns 文件完整元数据
 */
export async function finalizeUpload(
  workspaceId: string,
  payload: UploadFinalizeRequest,
): Promise<UploadedFileInfo> {
  const response = await fetch(buildUploadsUrl(workspaceId, "/finalize"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
    credentials: "include",
  });

  if (!response.ok) {
    throw new Error(
      await readErrorDetail(response, "Failed to finalize upload"),
    );
  }

  return response.json();
}

export async function uploadFileImmediately(
  workspaceId: string,
  file: File,
): Promise<UploadedFileInfo> {
  const prepare = await prepareUpload(workspaceId, {
    filename: file.name,
    content_type: file.type || null,
    size: file.size,
  });

  if (prepare.mode === "direct") {
    await uploadDirectFile(prepare, file);
    return finalizeUpload(workspaceId, {
      filename: prepare.file.filename,
      object_key: prepare.file.object_key,
      size: file.size,
    });
  }

  const uploadResponse = await uploadFiles(workspaceId, [file]);
  const uploadedFile = uploadResponse.files[0];
  if (!uploadedFile) {
    throw new Error("Upload finished without returning file metadata.");
  }
  return uploadedFile;
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

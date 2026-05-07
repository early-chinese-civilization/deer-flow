import type { FileInMessage } from "../messages/utils";

import type { UploadedFileInfo } from "./api";

export type ComposerUploadState =
  | "pending"
  | "uploading"
  | "uploaded"
  | "error";

export interface ComposerUploadAttachment {
  uploadState?: ComposerUploadState;
  uploadedFile?: UploadedFileInfo | null;
}

export type RetryableComposerUploadAttachment = ComposerUploadAttachment & {
  uploadError?: string | null;
};

export function getCanonicalUploadedFilePath(file: UploadedFileInfo): string {
  if (!file.oss_uri) {
    throw new Error("Uploaded file is missing oss uri.");
  }

  return file.oss_uri;
}

export function hasBlockingAttachmentUploads(
  attachments: ComposerUploadAttachment[],
): boolean {
  return attachments.some(
    (attachment) => attachment.uploadState !== "uploaded",
  );
}

export function buildMessageFilesFromAttachments(
  attachments: ComposerUploadAttachment[],
): FileInMessage[] {
  return attachments.flatMap((attachment) => {
    if (attachment.uploadState !== "uploaded" || !attachment.uploadedFile) {
      return [];
    }

    return [
      {
        filename: attachment.uploadedFile.filename,
        size: attachment.uploadedFile.size,
        path: getCanonicalUploadedFilePath(attachment.uploadedFile),
        virtual_path: attachment.uploadedFile.virtual_path,
        http_uri:
          attachment.uploadedFile.http_uri ?? attachment.uploadedFile.artifact_url ?? null,
        oss_uri: attachment.uploadedFile.oss_uri,
        object_key: attachment.uploadedFile.object_key,
        markdown_http_uri: attachment.uploadedFile.markdown_http_uri,
        status: "uploaded" as const,
      },
    ];
  });
}

export function resetAttachmentForRetry<
  T extends RetryableComposerUploadAttachment,
>(attachment: T): T {
  return {
    ...attachment,
    uploadState: "pending",
    uploadError: null,
    uploadedFile: null,
  };
}

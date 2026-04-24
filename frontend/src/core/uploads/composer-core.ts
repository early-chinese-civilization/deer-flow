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

export function hasBlockingAttachmentUploads(
  attachments: ComposerUploadAttachment[],
): boolean {
  return attachments.some((attachment) => attachment.uploadState !== "uploaded");
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
        path: attachment.uploadedFile.virtual_path,
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

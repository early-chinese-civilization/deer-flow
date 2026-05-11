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

export type DraftComposerWorkspace = {
  draftKey: string;
  workspaceId: string;
};

export const MAX_COMPOSER_UPLOAD_FILE_SIZE_BYTES = 100 * 1024 * 1024;
export const MAX_COMPOSER_UPLOAD_FILE_SIZE_LABEL = "100MB";

export function isComposerUploadFileWithinLimit(
  { size }: Pick<File, "size">,
  limitBytes = MAX_COMPOSER_UPLOAD_FILE_SIZE_BYTES,
): boolean {
  return size <= limitBytes;
}

export function filterComposerUploadFilesBySizeLimit<
  T extends Pick<File, "name" | "size">,
>(
  files: T[],
  limitBytes = MAX_COMPOSER_UPLOAD_FILE_SIZE_BYTES,
): {
  accepted: T[];
  rejected: T[];
} {
  return files.reduce<{
    accepted: T[];
    rejected: T[];
  }>(
    (result, file) => {
      if (isComposerUploadFileWithinLimit(file, limitBytes)) {
        result.accepted.push(file);
      } else {
        result.rejected.push(file);
      }
      return result;
    },
    { accepted: [], rejected: [] },
  );
}

export function getCanonicalUploadedFilePath(file: UploadedFileInfo): string {
  if (!file.oss_uri) {
    throw new Error("Uploaded file is missing oss uri.");
  }

  return file.oss_uri;
}

export function resolveDraftComposerWorkspaceId(
  draftWorkspace: DraftComposerWorkspace | null,
  draftKey?: string | null,
): string | null {
  if (!draftKey || draftWorkspace?.draftKey !== draftKey) {
    return null;
  }

  return draftWorkspace.workspaceId;
}

export function hasBlockingAttachmentUploads(
  attachments: ComposerUploadAttachment[],
): boolean {
  return attachments.some(
    (attachment) => attachment.uploadState !== "uploaded",
  );
}

export function canSubmitComposerMessage({
  text,
  attachments,
}: {
  text: string;
  attachments: ComposerUploadAttachment[];
}): boolean {
  if (hasBlockingAttachmentUploads(attachments)) {
    return false;
  }

  return text.trim().length > 0 || attachments.length > 0;
}

export function assertCanSubmitComposerMessage({
  text,
  attachments,
}: {
  text: string;
  attachments: ComposerUploadAttachment[];
}): void {
  if (!canSubmitComposerMessage({ text, attachments })) {
    throw new Error("Composer message is not ready to submit.");
  }
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
          attachment.uploadedFile.http_uri ??
          attachment.uploadedFile.artifact_url ??
          null,
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

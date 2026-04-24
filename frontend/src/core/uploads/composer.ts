import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import { usePromptInputAttachments } from "../../components/ai-elements/prompt-input";
import { uuid } from "../utils/uuid";

import type { ListFilesResponse } from "./api";
import { uploadFileImmediately } from "./api";
import { addUploadedFilesToList } from "./cache";
import { hasBlockingAttachmentUploads } from "./composer-core";

export function useComposerAttachmentUploads(options: {
  persistedWorkspaceId?: string | null;
}) {
  const { persistedWorkspaceId = null } = options;
  const attachments = usePromptInputAttachments();
  const queryClient = useQueryClient();
  const [draftWorkspaceId, setDraftWorkspaceId] = useState<string | null>(null);

  useEffect(() => {
    if (!persistedWorkspaceId) {
      return;
    }
    setDraftWorkspaceId(persistedWorkspaceId);
  }, [persistedWorkspaceId]);

  useEffect(() => {
    const pendingAttachments = attachments.files.filter(
      (attachment) =>
        attachment.sourceFile && attachment.uploadState === "pending",
    );
    if (pendingAttachments.length === 0) {
      return;
    }

    let targetWorkspaceId = persistedWorkspaceId ?? draftWorkspaceId;
    if (!targetWorkspaceId) {
      targetWorkspaceId = uuid();
      setDraftWorkspaceId(targetWorkspaceId);
    }

    for (const attachment of pendingAttachments) {
      attachments.update(attachment.id, (current) => ({
        ...current,
        uploadState: "uploading",
        uploadError: null,
      }));

      void uploadFileImmediately(targetWorkspaceId, attachment.sourceFile!)
        .then((uploadedFile) => {
          attachments.update(attachment.id, (current) => ({
            ...current,
            filename: uploadedFile.filename,
            uploadState: "uploaded",
            uploadError: null,
            uploadedFile,
          }));

          queryClient.setQueriesData<ListFilesResponse | undefined>(
            { queryKey: ["uploads", "list", targetWorkspaceId] },
            (current) => addUploadedFilesToList(current, [uploadedFile]),
          );
        })
        .catch((error) => {
          attachments.update(attachment.id, (current) => ({
            ...current,
            uploadState: "error",
            uploadError:
              error instanceof Error ? error.message : "Upload failed.",
            uploadedFile: null,
          }));
        });
    }
  }, [attachments, draftWorkspaceId, persistedWorkspaceId, queryClient]);

  const isUploading = useMemo(
    () =>
      attachments.files.some(
        (attachment) =>
          attachment.uploadState === "pending" ||
          attachment.uploadState === "uploading",
      ),
    [attachments.files],
  );

  return {
    attachments: attachments.files,
    composerWorkspaceId: persistedWorkspaceId ?? draftWorkspaceId,
    hasBlockingUploads: hasBlockingAttachmentUploads(attachments.files),
    isUploading,
  };
}

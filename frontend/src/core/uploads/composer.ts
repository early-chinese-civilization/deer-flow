import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import { usePromptInputAttachments } from "../../components/ai-elements/prompt-input";
import { uuid } from "../utils/uuid";

import type { ListFilesResponse } from "./api";
import { uploadFileImmediately } from "./api";
import { addUploadedFilesToList } from "./cache";
import {
  hasBlockingAttachmentUploads,
  resolveDraftComposerWorkspaceId,
  type DraftComposerWorkspace,
} from "./composer-core";

export function useComposerAttachmentUploads(options: {
  draftKey?: string | null;
  persistedWorkspaceId?: string | null;
}) {
  const { draftKey = null, persistedWorkspaceId = null } = options;
  const attachments = usePromptInputAttachments();
  const queryClient = useQueryClient();
  const [draftWorkspace, setDraftWorkspace] =
    useState<DraftComposerWorkspace | null>(null);
  const currentDraftWorkspaceId = resolveDraftComposerWorkspaceId(
    draftWorkspace,
    draftKey,
  );

  useEffect(() => {
    const pendingAttachments = attachments.files.filter(
      (attachment) =>
        attachment.sourceFile && attachment.uploadState === "pending",
    );
    if (pendingAttachments.length === 0) {
      return;
    }

    let targetWorkspaceId = persistedWorkspaceId ?? currentDraftWorkspaceId;
    if (!targetWorkspaceId && draftKey) {
      targetWorkspaceId = uuid();
      setDraftWorkspace({ draftKey, workspaceId: targetWorkspaceId });
    }
    if (!targetWorkspaceId) {
      return;
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
  }, [
    attachments,
    currentDraftWorkspaceId,
    draftKey,
    persistedWorkspaceId,
    queryClient,
  ]);

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
    composerWorkspaceId: persistedWorkspaceId ?? currentDraftWorkspaceId,
    hasBlockingUploads: hasBlockingAttachmentUploads(attachments.files),
    isUploading,
  };
}

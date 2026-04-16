/**
 * React hooks for file uploads
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";

import {
  deleteUploadedFile,
  listUploadedFiles,
  type ListFilesResponse,
  uploadFiles,
  type UploadedFileInfo,
  type UploadResponse,
} from "./api";
import { removeDeletedUploadedFilesFromList } from "./cache";

/**
 * Hook to upload files
 */
export function useUploadFiles(
  workspaceId: string,
  options?: {
    threadId?: string;
  },
) {
  const queryClient = useQueryClient();

  return useMutation<UploadResponse, Error, File[]>({
    mutationFn: (files: File[]) => uploadFiles(workspaceId, files, options),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: ["uploads", "list", workspaceId],
      });
    },
  });
}

/**
 * Hook to list uploaded files
 */
export function useUploadedFiles(
  workspaceId: string,
  options?: {
    threadId?: string;
  },
) {
  return useQuery({
    queryKey: ["uploads", "list", workspaceId, options?.threadId ?? null],
    queryFn: () => listUploadedFiles(workspaceId, options),
    enabled: !!workspaceId,
  });
}

/**
 * Hook to delete an uploaded file
 */
export function useDeleteUploadedFile(
  workspaceId: string,
  options?: {
    threadId?: string;
  },
) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (file: UploadedFileInfo) =>
      deleteUploadedFile(
        workspaceId,
        {
          filename: file.filename,
          object_key: file.object_key,
        },
        options,
      ),
    onSuccess: (_result, deletedFile) => {
      queryClient.setQueriesData<ListFilesResponse | undefined>(
        {
          queryKey: ["uploads", "list", workspaceId],
        },
        (current) =>
          removeDeletedUploadedFilesFromList(current, deletedFile),
      );
    },
  });
}

/**
 * Hook to handle file uploads in submit flow
 * Returns a function that uploads files and returns their info
 */
export function useUploadFilesOnSubmit(
  workspaceId: string,
  options?: {
    threadId?: string;
  },
) {
  const uploadMutation = useUploadFiles(workspaceId, options);

  return useCallback(
    async (files: File[]): Promise<UploadedFileInfo[]> => {
      if (files.length === 0) {
        return [];
      }

      const result = await uploadMutation.mutateAsync(files);
      return result.files;
    },
    [uploadMutation],
  );
}

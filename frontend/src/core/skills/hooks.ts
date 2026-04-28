import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { deleteSkill, downloadSkill, enableSkill, publishSkill, uploadSkills } from "./api";

import { loadSkills } from ".";

export function useSkills() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["skills"],
    queryFn: () => loadSkills(),
  });
  return { skills: data ?? [], isLoading, error };
}

export function useEnableSkill() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      skillName,
      enabled,
    }: {
      skillName: string;
      enabled: boolean;
    }) => {
      await enableSkill(skillName, enabled);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["skills"] });
    },
  });
}

export function useDeleteSkill() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (skillName: string) => deleteSkill(skillName),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["skills"] });
    },
  });
}

export function useUploadSkills() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      files,
      overwriteNames,
    }: {
      files: File[];
      overwriteNames: string[];
    }) => uploadSkills(files, overwriteNames),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["skills"] });
    },
  });
}

export function useDownloadSkill() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      skillName,
      ownerUserId,
      overwrite,
    }: {
      skillName: string;
      ownerUserId?: number | null;
      overwrite?: boolean;
    }) =>
      downloadSkill(skillName, {
        owner_user_id: ownerUserId,
        overwrite,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["skills"] });
    },
  });
}

export function usePublishSkill() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      skillName,
      releaseNotes,
    }: {
      skillName: string;
      releaseNotes?: string | null;
    }) => publishSkill(skillName, { release_notes: releaseNotes }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["skills"] });
    },
  });
}

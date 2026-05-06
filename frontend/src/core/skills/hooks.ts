import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  confirmSkillInstallUpdate,
  deleteSkill,
  enableSkill,
  installSkillHubSkill,
  previewSkillInstallUpdate,
  publishSkill,
  uploadSkills,
} from "./api";

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

export function useInstallSkillHubSkill() {
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
      installSkillHubSkill(skillName, {
        owner_user_id: ownerUserId,
        overwrite,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["skills"] });
    },
  });
}

export const useDownloadSkill = useInstallSkillHubSkill;

export function usePreviewSkillInstallUpdate(skillName: string | null) {
  return useQuery({
    queryKey: ["skills", "update-preview", skillName],
    queryFn: () => previewSkillInstallUpdate(skillName!),
    enabled: skillName !== null,
    staleTime: 0,
  });
}

export function useConfirmSkillInstallUpdate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      skillName,
      skillVersionId,
    }: {
      skillName: string;
      skillVersionId?: number | null;
    }) =>
      confirmSkillInstallUpdate(skillName, {
        skill_version_id: skillVersionId,
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

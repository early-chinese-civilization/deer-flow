import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  confirmSkillInstallUpdate,
  deleteSkill,
  downloadSkillForkPackage,
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
      skillDefinitionId,
      overwrite,
    }: {
      skillName: string;
      ownerUserId?: number | null;
      skillDefinitionId?: number | null;
      overwrite?: boolean;
    }) =>
      installSkillHubSkill(skillName, {
        owner_user_id: ownerUserId,
        skill_definition_id: skillDefinitionId,
        overwrite,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["skills"] });
      void queryClient.invalidateQueries({ queryKey: ["agents"] });
    },
  });
}

export const useDownloadSkill = useInstallSkillHubSkill;

export function useDownloadSkillForkPackage() {
  return useMutation({
    mutationFn: async ({
      skillName,
      ownerUserId,
      skillDefinitionId,
    }: {
      skillName: string;
      ownerUserId?: number | null;
      skillDefinitionId?: number | null;
    }) =>
      downloadSkillForkPackage(skillName, {
        owner_user_id: ownerUserId,
        skill_definition_id: skillDefinitionId,
      }),
  });
}

export function usePreviewSkillInstallUpdate(
  skillName: string | null,
  skillInstallId?: number | null,
) {
  return useQuery({
    queryKey: ["skills", "update-preview", skillName, skillInstallId ?? null],
    queryFn: () => previewSkillInstallUpdate(skillName!, skillInstallId),
    enabled: skillName !== null,
    staleTime: 0,
  });
}

export function useConfirmSkillInstallUpdate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      skillName,
      skillInstallId,
      skillVersionId,
    }: {
      skillName: string;
      skillInstallId?: number | null;
      skillVersionId?: number | null;
    }) =>
      confirmSkillInstallUpdate(skillName, {
        skill_install_id: skillInstallId,
        skill_version_id: skillVersionId,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["skills"] });
      void queryClient.invalidateQueries({ queryKey: ["agents"] });
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

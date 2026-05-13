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
      skillDefinitionId,
      skillInstallId,
    }: {
      skillName: string;
      enabled: boolean;
      skillDefinitionId?: number | null;
      skillInstallId?: number | null;
    }) => {
      await enableSkill(skillName, enabled, {
        skill_definition_id: skillDefinitionId,
        skill_install_id: skillInstallId,
      });
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["skills"] });
    },
  });
}

export function useDeleteSkill() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      skillName,
      skillDefinitionId,
      skillInstallId,
    }: {
      skillName: string;
      skillDefinitionId?: number | null;
      skillInstallId?: number | null;
    }) =>
      deleteSkill(skillName, {
        skill_definition_id: skillDefinitionId,
        skill_install_id: skillInstallId,
      }),
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
      skillId,
      versionNumber,
    }: {
      skillId: string;
      versionNumber: number;
    }) =>
      installSkillHubSkill({
        skill_id: skillId,
        version_number: versionNumber,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["skills"] });
      void queryClient.invalidateQueries({ queryKey: ["agents"] });
    },
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
      skillId,
      versionNumber,
    }: {
      skillName: string;
      skillInstallId: number;
      skillId: string;
      versionNumber: number;
    }) =>
      confirmSkillInstallUpdate(skillName, {
        skill_install_id: skillInstallId,
        skill_id: skillId,
        version_number: versionNumber,
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
      skillDefinitionId,
      releaseNotes,
    }: {
      skillName: string;
      skillDefinitionId?: number | null;
      releaseNotes?: string | null;
    }) =>
      publishSkill(skillName, {
        skill_definition_id: skillDefinitionId,
        release_notes: releaseNotes,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["skills"] });
    },
  });
}

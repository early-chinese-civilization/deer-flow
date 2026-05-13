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
      skillInstallationId,
    }: {
      skillName: string;
      enabled: boolean;
      skillInstallationId?: number | null;
    }) => {
      await enableSkill(skillName, enabled, {
        skill_installation_id: skillInstallationId,
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
      skillInstallationId,
    }: {
      skillName: string;
      skillInstallationId?: number | null;
    }) =>
      deleteSkill(skillName, {
        skill_installation_id: skillInstallationId,
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
  skillInstallationId?: number | null,
) {
  return useQuery({
    queryKey: [
      "skills",
      "update-preview",
      skillName,
      skillInstallationId ?? null,
    ],
    queryFn: () => previewSkillInstallUpdate(skillName!, skillInstallationId),
    enabled: skillName !== null,
    staleTime: 0,
  });
}

export function useConfirmSkillInstallUpdate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      skillName,
      skillInstallationId,
      skillId,
      versionNumber,
    }: {
      skillName: string;
      skillInstallationId?: number;
      skillId: string;
      versionNumber: number;
    }) => {
      const resolvedSkillInstallationId = skillInstallationId;
      if (resolvedSkillInstallationId == null) {
        throw new Error("Skill installation ID is required.");
      }
      return confirmSkillInstallUpdate(skillName, {
        skill_installation_id: resolvedSkillInstallationId,
        skill_id: skillId,
        version_number: versionNumber,
      });
    },
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
    }) =>
      publishSkill(skillName, {
        release_notes: releaseNotes,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["skills"] });
    },
  });
}

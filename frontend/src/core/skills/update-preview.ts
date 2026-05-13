import type { SkillInstallUpdatePreview } from "./api";

export interface SkillInstallUpdateDialogState {
  cancelDisabled: boolean;
  confirmDisabled: boolean;
  canConfirm: boolean;
}

export function getSkillInstallUpdateDialogState(
  preview: SkillInstallUpdatePreview | null,
  {
    isPreviewLoading,
    isConfirming,
  }: {
    isPreviewLoading: boolean;
    isConfirming: boolean;
  },
): SkillInstallUpdateDialogState {
  const canConfirm =
    preview?.status === "available" &&
    preview.target_platform_version != null &&
    preview.update_available;

  return {
    cancelDisabled: isConfirming,
    confirmDisabled: isConfirming || isPreviewLoading || !canConfirm,
    canConfirm,
  };
}

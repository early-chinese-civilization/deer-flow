import type { Skill } from "./type";

export type SkillInstallState =
  | "not-installed"
  | "installed"
  | "update-available";

export function getPlatformVersionNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && /^\d+$/.test(value)) {
    return Number(value);
  }
  return null;
}

export function getSkillPlatformVersion(skill: Skill): number | null {
  return (
    getPlatformVersionNumber(skill.current_platform_version) ??
    getPlatformVersionNumber(skill.installed_platform_version) ??
    getPlatformVersionNumber(skill.platform_version) ??
    getPlatformVersionNumber(skill.version)
  );
}

export interface AgentSkillDisplayFields {
  current_platform_version?: unknown;
  source?: string | null;
  source_label?: string | null;
  update_available?: boolean | null;
  available?: boolean | null;
  status?: string | null;
}

export function formatPlatformVersion(value: unknown): string | null {
  const version = getPlatformVersionNumber(value);
  return version == null ? null : `v${version}`;
}

export function getAgentSkillBindingPlatformVersion(
  skill: AgentSkillDisplayFields,
): number | null {
  return getPlatformVersionNumber(skill.current_platform_version);
}

export function isAgentSkillBindingUnavailable(
  skill: AgentSkillDisplayFields,
): boolean {
  return skill.available === false || skill.status === "unavailable";
}

export function getAgentSkillSourceLabel(
  skill: AgentSkillDisplayFields,
): string {
  const explicit = skill.source_label?.trim();
  if (explicit) {
    return explicit;
  }
  if (skill.source === "skillhub") {
    return "SkillHub";
  }
  if (skill.source === "my_skills") {
    return "My Skills";
  }
  return "Unknown source";
}

export function getSkillHubLatestPlatformVersion(skill: Skill): number | null {
  return (
    getPlatformVersionNumber(skill.latest_platform_version) ??
    getPlatformVersionNumber(skill.platform_version) ??
    getPlatformVersionNumber(skill.version)
  );
}

export function findInstalledSkillForSkillHubItem(
  skill: Skill,
  skills: Skill[],
): Skill | null {
  if (skill.category !== "public") {
    return skill.skill_install_id ? skill : null;
  }

  const byDefinition =
    skill.skill_definition_id != null
      ? skills.find(
          (candidate) =>
            candidate.category === "custom" &&
            candidate.skill_definition_id === skill.skill_definition_id &&
            candidate.skill_install_id != null,
        )
      : undefined;
  if (byDefinition) {
    return byDefinition;
  }

  return (
    skills.find(
      (candidate) =>
        candidate.category === "custom" &&
        candidate.name === skill.name &&
        candidate.skill_install_id != null,
    ) ?? null
  );
}

export function getInstalledPlatformVersion(
  skill: Skill,
  installedSkill: Skill | null,
): number | null {
  return (
    getPlatformVersionNumber(skill.current_platform_version) ??
    getPlatformVersionNumber(skill.installed_platform_version) ??
    (installedSkill ? getSkillPlatformVersion(installedSkill) : null)
  );
}

export function getSkillInstallState(
  skill: Skill,
  installedSkill: Skill | null = null,
): SkillInstallState {
  const installedVersion = getInstalledPlatformVersion(skill, installedSkill);
  const latestVersion = getSkillHubLatestPlatformVersion(skill);
  const isInstalled =
    skill.skill_install_id != null ||
    installedSkill?.skill_install_id != null ||
    installedVersion != null;

  if (!isInstalled) {
    return "not-installed";
  }

  if (skill.update_available === true) {
    return "update-available";
  }

  if (
    installedVersion != null &&
    latestVersion != null &&
    latestVersion > installedVersion
  ) {
    return "update-available";
  }

  return "installed";
}

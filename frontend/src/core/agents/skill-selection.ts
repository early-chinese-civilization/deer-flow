import { getSkillDisplayContract } from "../skills/display";
import type { Skill } from "../skills/type";

import type { AgentSkillMetadata } from "./types";

export interface AgentSkillSourceLabels {
  skillhub: string;
  mySkills: string;
  official: string;
  unknown: string;
}

export interface AgentSkillDisplaySummary {
  key: string;
  name: string;
  description: string;
  versionLabel: string;
  sourceLabel: string;
  updateAvailable: boolean;
  unavailable: boolean;
}

export interface AgentSkillSelectionGroups {
  mySkills: Skill[];
}

function getPlatformVersionNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && /^\d+$/.test(value)) {
    return Number(value);
  }
  return null;
}

function formatPlatformVersion(value: unknown): string | null {
  const version = getPlatformVersionNumber(value);
  return version == null ? null : `v${version}`;
}

function getSkillSelectionPlatformVersion(skill: Skill): number | null {
  return (
    getPlatformVersionNumber(skill.current_platform_version) ??
    getPlatformVersionNumber(skill.installed_platform_version) ??
    getPlatformVersionNumber(skill.platform_version)
  );
}

function hasSkillSelectionUpdate(skill: Skill, platformVersion: number | null) {
  const latestVersion = getPlatformVersionNumber(skill.latest_platform_version);
  return (
    skill.update_available === true ||
    (platformVersion != null &&
      latestVersion != null &&
      latestVersion > platformVersion)
  );
}

function compareSkillRows(left: Skill, right: Skill): number {
  if (left.name !== right.name) {
    return left.name.localeCompare(right.name);
  }
  return getSkillSelectionKey(left).localeCompare(getSkillSelectionKey(right));
}

export function getAgentSkillSelectionGroups(
  skills: Skill[],
): AgentSkillSelectionGroups {
  const mySkills: Skill[] = [];

  for (const skill of skills) {
    const display = getSkillDisplayContract(skill);
    if (display.space === "personal" && skill.skill_install_id != null) {
      mySkills.push(skill);
    }
  }

  return {
    mySkills: mySkills.sort(compareSkillRows),
  };
}

export function getSkillSelectionKey(skill: Skill): string {
  if (skill.skill_install_id != null) {
    return `install:${skill.skill_install_id}`;
  }
  if (skill.skill_id && skill.version_number != null) {
    return `unavailable:${skill.skill_id}:v${skill.version_number}`;
  }
  return `unavailable:${skill.name}`;
}

export function getMetadataSelectionKey(skill: AgentSkillMetadata): string {
  if (skill.skill_install_id != null) {
    return `install:${skill.skill_install_id}`;
  }
  return `unavailable:${skill.name}`;
}

export function getSelectionInstallIds(selection: string[]): number[] {
  const installIds: number[] = [];
  for (const value of selection) {
    if (!value.startsWith("install:")) {
      continue;
    }
    const installId = Number(value.slice("install:".length));
    if (Number.isInteger(installId)) {
      installIds.push(installId);
    }
  }
  return installIds;
}

export function getSelectionSkillNames(selection: string[]): string[] {
  void selection;
  return [];
}

export function getSkillSourceLabel(
  skill: Skill,
  labels: AgentSkillSourceLabels,
): string {
  const ownerDisplayName = skill.owner_display_name?.trim();
  if (ownerDisplayName) {
    return ownerDisplayName;
  }
  if (
    skill.source_kind === "official" ||
    skill.skill_definition_source_type === "legacy" ||
    (skill.category === "public" && skill.owner_user_id == null)
  ) {
    return labels.official;
  }
  if (skill.source_kind === "personal" || skill.source_kind === "fork") {
    return labels.mySkills;
  }
  if (skill.category === "public") {
    return labels.skillhub;
  }
  return labels.mySkills;
}

export function getMetadataSourceLabel(
  skill: AgentSkillMetadata,
  labels: AgentSkillSourceLabels,
): string {
  const explicit = skill.source_label?.trim();
  if (explicit) {
    return explicit;
  }
  if (skill.source === "skillhub") {
    return labels.skillhub;
  }
  if (skill.source === "my_skills") {
    return labels.mySkills;
  }
  if (skill.source === "system") {
    return labels.official;
  }
  return labels.unknown;
}

export function getSkillDisplaySummary(
  skill: Skill,
  labels: AgentSkillSourceLabels & { unavailableVersion: string },
): AgentSkillDisplaySummary {
  const platformVersion = getSkillSelectionPlatformVersion(skill);
  const unavailable =
    skill.skill_install_id == null ||
    skill.skill_id == null ||
    platformVersion == null;
  return {
    key: getSkillSelectionKey(skill),
    name: skill.name,
    description: skill.description,
    versionLabel:
      formatPlatformVersion(platformVersion) ?? labels.unavailableVersion,
    sourceLabel: getSkillSourceLabel(skill, labels),
    updateAvailable: hasSkillSelectionUpdate(skill, platformVersion),
    unavailable,
  };
}

export function getMetadataDisplaySummary(
  skill: AgentSkillMetadata,
  labels: AgentSkillSourceLabels & { unavailableVersion: string },
): AgentSkillDisplaySummary {
  return {
    key: getMetadataSelectionKey(skill),
    name: skill.name,
    description: "",
    versionLabel:
      formatPlatformVersion(skill.current_platform_version) ??
      labels.unavailableVersion,
    sourceLabel: getMetadataSourceLabel(skill, labels),
    updateAvailable: skill.update_available === true,
    unavailable: skill.available === false || skill.status === "unavailable",
  };
}

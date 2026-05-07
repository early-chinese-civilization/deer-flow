import type {
  Skill,
  SkillSourceKind,
  SkillSpace,
  SkillViewerRelation,
} from "./type";

export type SkillInstallState =
  | "not-installed"
  | "installed"
  | "update-available";

const SKILL_SPACES = ["community", "personal"] as const;
const SKILL_SOURCE_KINDS = [
  "official",
  "community",
  "personal",
  "fork",
] as const;
const SKILL_VIEWER_RELATIONS = [
  "official_available",
  "community_available",
  "downloaded",
  "authored",
  "authored_published",
  "authored_unpublished_changes",
  "update_available",
  "forked",
] as const;

export interface SkillDisplayContract {
  space: SkillSpace;
  sourceKind: SkillSourceKind;
  viewerRelation: SkillViewerRelation;
  identityKey: string;
}

function isSkillSpace(value: unknown): value is SkillSpace {
  return SKILL_SPACES.includes(value as SkillSpace);
}

function isSkillSourceKind(value: unknown): value is SkillSourceKind {
  return SKILL_SOURCE_KINDS.includes(value as SkillSourceKind);
}

function isSkillViewerRelation(value: unknown): value is SkillViewerRelation {
  return SKILL_VIEWER_RELATIONS.includes(value as SkillViewerRelation);
}

function getLegacySkillSpace(skill: Skill): SkillSpace {
  return skill.category === "public" ? "community" : "personal";
}

function getLegacySkillSourceKind(
  skill: Skill,
  space: SkillSpace,
): SkillSourceKind {
  if (
    (space === "community" && skill.owner_user_id == null) ||
    skill.skill_definition_source_type === "legacy"
  ) {
    return "official";
  }
  if (space === "personal") {
    return skill.skill_install_id != null ? "community" : "personal";
  }
  return "community";
}

function getLegacySkillViewerRelation(
  skill: Skill,
  space: SkillSpace,
  sourceKind: SkillSourceKind,
): SkillViewerRelation {
  if (sourceKind === "fork") {
    return "forked";
  }
  if (skill.update_available === true) {
    return "update_available";
  }
  if (space === "community") {
    return sourceKind === "official"
      ? "official_available"
      : "community_available";
  }
  if (skill.skill_install_id != null && sourceKind !== "personal") {
    return "downloaded";
  }
  if (skill.release_status === "published") {
    return "authored_published";
  }
  return "authored";
}

export function getSkillDisplayContract(skill: Skill): SkillDisplayContract {
  const space = isSkillSpace(skill.space)
    ? skill.space
    : getLegacySkillSpace(skill);
  const sourceKind = isSkillSourceKind(skill.source_kind)
    ? skill.source_kind
    : getLegacySkillSourceKind(skill, space);
  const viewerRelation = isSkillViewerRelation(skill.viewer_relation)
    ? skill.viewer_relation
    : getLegacySkillViewerRelation(skill, space, sourceKind);

  return {
    space,
    sourceKind,
    viewerRelation,
    identityKey: getSkillIdentityKey(skill),
  };
}

export function getSkillIdentityKey(skill: Skill): string {
  const space = isSkillSpace(skill.space)
    ? skill.space
    : getLegacySkillSpace(skill);
  if (space === "personal" && skill.skill_install_id != null) {
    return `install:${skill.skill_install_id}`;
  }
  if (skill.skill_definition_id != null) {
    return `definition:${skill.skill_definition_id}`;
  }
  if (skill.skill_install_id != null) {
    return `install:${skill.skill_install_id}`;
  }
  if (skill.skill_version_id != null) {
    return `version:${skill.skill_version_id}`;
  }
  const sourceKind = isSkillSourceKind(skill.source_kind)
    ? skill.source_kind
    : getLegacySkillSourceKind(skill, space);
  return `legacy:${space}:${sourceKind}:${skill.owner_user_id ?? "system"}:${skill.name}`;
}

export function isCommunitySkill(skill: Skill): boolean {
  return getSkillDisplayContract(skill).space === "community";
}

export function isPersonalSkill(skill: Skill): boolean {
  return getSkillDisplayContract(skill).space === "personal";
}

export function isAuthoredSkillRelation(skill: Skill): boolean {
  const relation = getSkillDisplayContract(skill).viewerRelation;
  return (
    relation === "authored" ||
    relation === "authored_published" ||
    relation === "authored_unpublished_changes" ||
    relation === "forked"
  );
}

export function isSelfAuthoredCommunitySkill(skill: Skill): boolean {
  const display = getSkillDisplayContract(skill);
  return (
    display.space === "community" &&
    (display.viewerRelation === "authored_published" ||
      display.viewerRelation === "authored_unpublished_changes")
  );
}

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
  if (!isCommunitySkill(skill)) {
    return skill.skill_install_id ? skill : null;
  }

  const byDefinition =
    skill.skill_definition_id != null
      ? skills.find(
          (candidate) =>
            isPersonalSkill(candidate) &&
            candidate.skill_definition_id === skill.skill_definition_id &&
            candidate.skill_install_id != null,
        )
      : undefined;
  if (byDefinition) {
    return byDefinition;
  }

  const sameNameCandidates = skills.filter(
    (candidate) =>
      isPersonalSkill(candidate) &&
      candidate.name === skill.name &&
      candidate.skill_install_id != null,
  );
  const onlyMatch = sameNameCandidates[0];
  return sameNameCandidates.length === 1 && onlyMatch ? onlyMatch : null;
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

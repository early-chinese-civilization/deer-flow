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

export type SkillWorkspaceSegment =
  | "all"
  | "installed"
  | "authored"
  | "updates";

export type SkillWorkspaceCardRole =
  | "system"
  | "community"
  | "self-published-community"
  | "installed"
  | "authored"
  | "authored-published"
  | "authored-unpublished-changes";

export type SkillWorkspacePrimaryAction =
  | "add-to-personal"
  | "view-personal"
  | "view-update"
  | "publish"
  | "publish-update"
  | "none";

export interface SkillDisplayContract {
  space: SkillSpace;
  sourceKind: SkillSourceKind;
  viewerRelation: SkillViewerRelation;
  identityKey: string;
}

export interface SkillWorkspaceCardState {
  role: SkillWorkspaceCardRole;
  primaryAction: SkillWorkspacePrimaryAction;
  segments: SkillWorkspaceSegment[];
}

export function getSkillInstallationId(skill: Skill): number | null {
  return skill.skill_installation_id ?? null;
}

export function getSkillDisplayContract(skill: Skill): SkillDisplayContract {
  const explicitSpace = skill.space;
  const sourceKind = skill.source_kind;
  const viewerRelation = skill.viewer_relation;
  const space =
    sourceKind === "official" ||
    viewerRelation === "official_available" ||
    viewerRelation === "system_available"
      ? "system"
      : explicitSpace;

  return {
    space,
    sourceKind,
    viewerRelation,
    identityKey: getSkillIdentityKey(skill),
  };
}

export function getSkillIdentityKey(skill: Skill): string {
  const explicitSpace = skill.space;
  const explicitSourceKind = skill.source_kind;
  const explicitViewerRelation = skill.viewer_relation;
  const space =
    explicitSourceKind === "official" ||
    explicitViewerRelation === "official_available" ||
    explicitViewerRelation === "system_available"
      ? "system"
      : explicitSpace;
  const skillInstallationId = getSkillInstallationId(skill);
  if (space === "personal" && skillInstallationId != null) {
    return `install:${skillInstallationId}`;
  }
  if (skill.skill_id && skill.version_number != null) {
    return `skill:${skill.skill_id}:v${skill.version_number}`;
  }
  if (skill.skill_id) {
    return `skill:${skill.skill_id}`;
  }
  if (skillInstallationId != null) {
    return `install:${skillInstallationId}`;
  }
  return `legacy:${space}:${explicitSourceKind}:${skill.owner_user_id ?? "system"}:${skill.name}`;
}

export function isCommunitySkill(skill: Skill): boolean {
  return getSkillDisplayContract(skill).space === "community";
}

export function isSystemSkill(skill: Skill): boolean {
  return getSkillDisplayContract(skill).space === "system";
}

export function isPersonalSkill(skill: Skill): boolean {
  return getSkillDisplayContract(skill).space === "personal";
}

export function isAuthoredSkillRelation(skill: Skill): boolean {
  const relation = getSkillDisplayContract(skill).viewerRelation;
  return (
    relation === "authored" ||
    relation === "authored_published" ||
    relation === "authored_unpublished_changes"
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

export function isInstalledCommunitySkillRelation(skill: Skill): boolean {
  const display = getSkillDisplayContract(skill);
  return (
    display.space === "personal" &&
    (display.viewerRelation === "installed" ||
      display.viewerRelation === "update_available")
  );
}

export function getSkillWorkspaceCardState(
  skill: Skill,
  installedSkill: Skill | null = null,
): SkillWorkspaceCardState {
  const display = getSkillDisplayContract(skill);
  const segments = new Set<SkillWorkspaceSegment>(["all"]);

  if (display.space === "system") {
    return {
      role: "system",
      primaryAction: "none",
      segments: Array.from(segments),
    };
  }

  if (display.space === "community") {
    const installState = getSkillInstallState(skill, installedSkill);

    if (isSelfAuthoredCommunitySkill(skill)) {
      return {
        role: "self-published-community",
        primaryAction: "none",
        segments: Array.from(segments),
      };
    }

    if (installState !== "not-installed") {
      return {
        role: "community",
        primaryAction: "none",
        segments: Array.from(segments),
      };
    }

    return {
      role: "community",
      primaryAction: "add-to-personal",
      segments: Array.from(segments),
    };
  }

  if (display.viewerRelation === "update_available") {
    segments.add("installed");
    segments.add("updates");
    return {
      role: "installed",
      primaryAction: "view-update",
      segments: Array.from(segments),
    };
  }

  if (display.viewerRelation === "installed") {
    segments.add("installed");
    return {
      role: "installed",
      primaryAction: "none",
      segments: Array.from(segments),
    };
  }

  if (display.viewerRelation === "authored_unpublished_changes") {
    segments.add("authored");
    segments.add("updates");
    return {
      role: "authored-unpublished-changes",
      primaryAction: "publish-update",
      segments: Array.from(segments),
    };
  }

  if (display.viewerRelation === "authored_published") {
    segments.add("authored");
    return {
      role: "authored-published",
      primaryAction: "none",
      segments: Array.from(segments),
    };
  }

  segments.add("authored");
  return {
    role: "authored",
    primaryAction: "publish",
    segments: Array.from(segments),
  };
}

export function skillMatchesWorkspaceSegment(
  skill: Skill,
  segment: SkillWorkspaceSegment,
  installedSkill: Skill | null = null,
): boolean {
  if (segment === "all") {
    return true;
  }
  return getSkillWorkspaceCardState(skill, installedSkill).segments.includes(
    segment,
  );
}

function normalizeSearchText(value: string | null | undefined): string {
  return value?.trim().toLowerCase() ?? "";
}

export function skillMatchesCommunitySearch(
  skill: Skill,
  searchQuery: string,
): boolean {
  if (!isCommunitySkill(skill)) {
    return false;
  }

  const terms = normalizeSearchText(searchQuery).split(/\s+/).filter(Boolean);
  if (terms.length === 0) {
    return true;
  }

  const display = getSkillDisplayContract(skill);
  const searchableFields = [
    skill.name,
    skill.owner_display_name,
    display.sourceKind,
    display.sourceKind === "official" ? "official" : null,
  ]
    .map(normalizeSearchText)
    .filter(Boolean);

  return terms.every((term) =>
    searchableFields.some((field) => field.includes(term)),
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
    return getSkillInstallationId(skill) ? skill : null;
  }

  const bySkillId =
    skill.skill_id != null
      ? skills.find(
          (candidate) =>
            isPersonalSkill(candidate) &&
            candidate.skill_id === skill.skill_id &&
            getSkillInstallationId(candidate) != null,
        )
      : undefined;
  if (bySkillId) {
    return bySkillId;
  }

  return null;
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
    getSkillInstallationId(skill) != null ||
    (installedSkill ? getSkillInstallationId(installedSkill) != null : false) ||
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

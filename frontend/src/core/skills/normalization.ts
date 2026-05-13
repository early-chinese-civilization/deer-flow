import type {
  Skill,
  SkillSourceKind,
  SkillSpace,
  SkillViewerRelation,
} from "./type";

type LegacySkillCategory = "public" | "custom";
type LegacySkillSourceKind = "fork";
type LegacySkillViewerRelation = "downloaded" | "forked";

export type SkillApiResponse = Omit<
  Skill,
  "space" | "source_kind" | "viewer_relation" | "skill_installation_id"
> & {
  category?: LegacySkillCategory | null;
  space?: SkillSpace | null;
  source_kind?: SkillSourceKind | LegacySkillSourceKind | null;
  viewer_relation?: SkillViewerRelation | LegacySkillViewerRelation | null;
  skill_installation_id?: number | null;
  skill_install_id?: number | null;
};

const legacySourceKindMap = {
  fork: "personal",
} satisfies Record<LegacySkillSourceKind, SkillSourceKind>;

const legacyViewerRelationMap = {
  downloaded: "installed",
  forked: "authored",
} satisfies Record<LegacySkillViewerRelation, SkillViewerRelation>;

function normalizeSpaceFromApi(raw: SkillApiResponse): SkillSpace {
  return (
    raw.space ??
    (raw.skill_definition_source_type === "legacy" ||
    (raw.category === "public" && raw.owner_user_id == null)
      ? "system"
      : raw.category === "public"
        ? "community"
        : "personal")
  );
}

function normalizeSourceKindFromApi(
  raw: SkillApiResponse,
  space: SkillSpace,
  skillInstallationId: number | null,
): SkillSourceKind {
  if (raw.source_kind === "fork") {
    return legacySourceKindMap[raw.source_kind];
  }
  return (
    raw.source_kind ??
    (space === "system"
      ? "official"
      : space === "personal" && skillInstallationId == null
        ? "personal"
        : "community")
  );
}

function normalizeViewerRelationFromApi(
  raw: SkillApiResponse,
  space: SkillSpace,
  sourceKind: SkillSourceKind,
): SkillViewerRelation {
  if (raw.viewer_relation === "downloaded" || raw.viewer_relation === "forked") {
    return legacyViewerRelationMap[raw.viewer_relation];
  }
  return (
    raw.viewer_relation ??
    (space === "system"
      ? "system_available"
      : space === "community"
        ? "community_available"
        : sourceKind === "personal"
          ? "authored"
          : "installed")
  );
}

export function normalizeSkillFromApi(raw: SkillApiResponse): Skill {
  const skillInstallationId =
    raw.skill_installation_id ?? raw.skill_install_id ?? null;
  const space = normalizeSpaceFromApi(raw);
  const sourceKind = normalizeSourceKindFromApi(
    raw,
    space,
    skillInstallationId,
  );
  const viewerRelation = normalizeViewerRelationFromApi(
    raw,
    space,
    sourceKind,
  );

  return {
    ...raw,
    space,
    source_kind: sourceKind,
    viewer_relation: viewerRelation,
    skill_installation_id: skillInstallationId,
  };
}

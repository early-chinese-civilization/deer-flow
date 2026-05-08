export type SkillSpace = "system" | "community" | "personal";
export type SkillSourceKind = "official" | "community" | "personal" | "fork";
export type SkillViewerRelation =
  | "system_available"
  | "official_available"
  | "community_available"
  | "downloaded"
  | "authored"
  | "authored_published"
  | "authored_unpublished_changes"
  | "update_available"
  | "forked";

export interface Skill {
  name: string;
  description: string;
  category: "public" | "custom";
  space?: SkillSpace | null;
  source_kind?: SkillSourceKind | null;
  viewer_relation?: SkillViewerRelation | null;
  license: string | null;
  enabled: boolean;
  version?: string | null;
  platform_version?: number | null;
  skill_definition_id?: number | null;
  skill_definition_source_type?: string | null;
  skill_definition_source_identifier?: string | null;
  skill_version_id?: number | null;
  skill_install_id?: number | null;
  current_platform_version?: number | null;
  installed_platform_version?: number | null;
  latest_platform_version?: number | null;
  update_available?: boolean | null;
  source_package_version?: string | null;
  package_version?: string | null;
  release_version?: string | null;
  release_status?: "published" | null;
  release_notes?: string | null;
  published_at?: string | null;
  fork_source_skill_name?: string | null;
  fork_source_owner_display_name?: string | null;
  fork_source_platform_version?: number | null;
  fork_source_skill_version_id?: number | null;
  owner_user_id?: number | null;
  owner_display_name?: string | null;
}

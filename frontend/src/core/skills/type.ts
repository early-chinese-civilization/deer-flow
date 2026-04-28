export interface Skill {
  name: string;
  description: string;
  category: "public" | "custom";
  license: string | null;
  enabled: boolean;
  version?: string | null;
  package_version?: string | null;
  release_version?: string | null;
  release_status?: "published" | null;
  release_notes?: string | null;
  published_at?: string | null;
  owner_user_id?: number | null;
  owner_display_name?: string | null;
}

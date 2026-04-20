export interface Skill {
  name: string;
  description: string;
  category: string;
  license: string | null;
  enabled: boolean;
  owner_user_id?: number | null;
  owner_display_name?: string | null;
}

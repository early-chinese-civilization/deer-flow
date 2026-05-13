export type AgentSkillSource = "system" | "skillhub" | "my_skills" | "unknown";

export type AgentSkillStatus = "available" | "unavailable";

export interface AgentSkillMetadata {
  name: string;
  skill_installation_id: number | null;
  current_platform_version: number | null;
  source: AgentSkillSource;
  source_label: string;
  update_available: boolean | null;
  available: boolean;
  status: AgentSkillStatus;
}

export interface Agent {
  name: string;
  description: string;
  skills: string[] | null;
  skill_metadata?: AgentSkillMetadata[] | null;
  soul?: string | null;
}

export type AgentDraftMode = "create" | "edit";

export type AgentDraftStatus = "active" | "finalized" | "abandoned";

export interface AgentDraftPayload {
  name: string;
  description: string;
  soul: string;
  skills: string[];
}

export interface AgentDraft {
  id: string;
  mode: AgentDraftMode;
  target_agent_id: number | null;
  target_agent_name: string | null;
  base_agent_updated_at: string | null;
  payload: AgentDraftPayload;
  status: AgentDraftStatus;
  created_at: string;
  updated_at: string;
}

export interface AgentDraftPatchRequest {
  name?: string;
  description?: string;
  soul?: string;
  skills?: string[];
}

export interface CreateAgentRequest {
  name: string;
  description?: string;
  skill_installation_ids?: number[] | null;
  soul?: string;
}

export interface UpdateAgentRequest {
  description?: string | null;
  skill_installation_ids?: number[] | null;
  soul?: string | null;
}

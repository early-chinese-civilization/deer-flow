export interface Agent {
  name: string;
  description: string;
  skills: string[] | null;
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
  skills?: string[] | null;
  soul?: string;
}

export interface UpdateAgentRequest {
  description?: string | null;
  skills?: string[] | null;
  soul?: string | null;
}

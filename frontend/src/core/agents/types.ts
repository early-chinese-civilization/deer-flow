export interface Agent {
  name: string;
  description: string;
  skills: string[] | null;
  soul?: string | null;
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

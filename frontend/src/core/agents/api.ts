import { BRAND } from "@/core/brand";
import { getBackendBaseURL } from "@/core/config";

import type { Agent, CreateAgentRequest, UpdateAgentRequest } from "./types";

const BACKEND_UNAVAILABLE_STATUSES = new Set([502, 503, 504]);
const BACKEND_UNREACHABLE_MESSAGE = `Could not reach the ${BRAND.en.shortName} backend.`;

export class AgentNameCheckError extends Error {
  constructor(
    message: string,
    public readonly reason: "backend_unreachable" | "request_failed",
  ) {
    super(message);
    this.name = "AgentNameCheckError";
  }
}

async function readErrorDetail(
  response: Response,
  fallback: string,
): Promise<never> {
  const err = (await response.json().catch(() => ({}))) as { detail?: string };
  throw new Error(err.detail ?? fallback);
}

export async function listAgents(): Promise<Agent[]> {
  const res = await fetch(`${getBackendBaseURL()}/api/agents`, {
    credentials: "include",
  });
  if (!res.ok) throw new Error(`Failed to load agents: ${res.statusText}`);
  const data = (await res.json()) as { agents: Agent[] };
  return data.agents;
}

export async function getAgent(name: string): Promise<Agent> {
  const res = await fetch(`${getBackendBaseURL()}/api/agents/${name}`, {
    credentials: "include",
  });
  if (!res.ok) throw new Error(`Agent '${name}' not found`);
  return res.json() as Promise<Agent>;
}

export async function createAgent(request: CreateAgentRequest): Promise<Agent> {
  const res = await fetch(`${getBackendBaseURL()}/api/agents`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
    credentials: "include",
  });
  if (!res.ok) {
    return readErrorDetail(res, `Failed to create agent: ${res.statusText}`);
  }
  return res.json() as Promise<Agent>;
}

export async function updateAgent(
  name: string,
  request: UpdateAgentRequest,
): Promise<Agent> {
  const res = await fetch(`${getBackendBaseURL()}/api/agents/${name}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
    credentials: "include",
  });
  if (!res.ok) {
    return readErrorDetail(res, `Failed to update agent: ${res.statusText}`);
  }
  return res.json() as Promise<Agent>;
}

export async function deleteAgent(name: string): Promise<void> {
  const res = await fetch(`${getBackendBaseURL()}/api/agents/${name}`, {
    method: "DELETE",
    credentials: "include",
  });
  if (!res.ok) throw new Error(`Failed to delete agent: ${res.statusText}`);
}

export async function checkAgentName(
  name: string,
): Promise<{ available: boolean; name: string }> {
  let res: Response;
  try {
    res = await fetch(
      `${getBackendBaseURL()}/api/agents/check?name=${encodeURIComponent(name)}`,
      {
        credentials: "include",
      },
    );
  } catch {
    throw new AgentNameCheckError(
      BACKEND_UNREACHABLE_MESSAGE,
      "backend_unreachable",
    );
  }

  if (!res.ok) {
    const err = (await res.json().catch(() => ({}))) as { detail?: string };
    if (BACKEND_UNAVAILABLE_STATUSES.has(res.status)) {
      throw new AgentNameCheckError(
        BACKEND_UNREACHABLE_MESSAGE,
        "backend_unreachable",
      );
    }
    throw new AgentNameCheckError(
      err.detail ?? `Failed to check agent name: ${res.statusText}`,
      "request_failed",
    );
  }
  return res.json() as Promise<{ available: boolean; name: string }>;
}

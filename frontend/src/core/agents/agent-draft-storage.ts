import type { AgentDraftFormState } from "./agent-draft-lifecycle";
import type { AgentDraftMode } from "./types";

interface StoredAgentDraft {
  mode: AgentDraftMode;
  agentName: string | null;
  payload: AgentDraftFormState;
  updatedAt: string;
}

const CREATE_DRAFT_KEY = "deer-flow.agent-draft.create";
const EDIT_DRAFT_PREFIX = "deer-flow.agent-draft.edit";

export function getAgentDraftStorageKey(
  mode: AgentDraftMode,
  agentName?: string | null,
): string {
  if (mode === "create") {
    return CREATE_DRAFT_KEY;
  }
  return `${EDIT_DRAFT_PREFIX}.${agentName ?? ""}`;
}

export function readStoredAgentDraft(
  storage: Storage,
  mode: AgentDraftMode,
  agentName?: string | null,
): StoredAgentDraft | null {
  try {
    const raw = storage.getItem(getAgentDraftStorageKey(mode, agentName));
    if (!raw) {
      return null;
    }
    const parsed = JSON.parse(raw) as Partial<StoredAgentDraft>;
    if (!parsed || typeof parsed !== "object" || !parsed.payload) {
      return null;
    }
    return {
      mode,
      agentName: parsed.agentName ?? null,
      payload: {
        name: parsed.payload.name ?? "",
        description: parsed.payload.description ?? "",
        soul: parsed.payload.soul ?? "",
        skills: Array.isArray(parsed.payload.skills) ? parsed.payload.skills : [],
      },
      updatedAt: parsed.updatedAt ?? "",
    };
  } catch {
    return null;
  }
}

export function writeStoredAgentDraft(
  storage: Storage,
  {
    mode,
    agentName,
    payload,
  }: {
    mode: AgentDraftMode;
    agentName: string | null;
    payload: AgentDraftFormState;
  },
): void {
  storage.setItem(
    getAgentDraftStorageKey(mode, agentName),
    JSON.stringify({
      mode,
      agentName,
      payload,
      updatedAt: new Date().toISOString(),
    } satisfies StoredAgentDraft),
  );
}

export function clearStoredAgentDraft(
  storage: Storage,
  mode: AgentDraftMode,
  agentName?: string | null,
): void {
  storage.removeItem(getAgentDraftStorageKey(mode, agentName));
}

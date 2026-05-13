import type {
  AgentDraftMode,
  AgentDraftPatchRequest,
  AgentDraftPayload,
} from "./types";

export const AGENT_DRAFT_TABS = [
  "name",
  "description",
  "soul",
  "skills",
  "confirm",
] as const;

export type AgentDraftTab = (typeof AGENT_DRAFT_TABS)[number];
export type AgentDraftInputTab = Exclude<AgentDraftTab, "confirm">;

export interface AgentDraftFormState {
  name: string;
  description: string;
  soul: string;
  skills: string[];
}

function orderedUniqueSkillSelectionKeys(
  skillSelectionKeys: string[] | null | undefined,
): string[] {
  if (!skillSelectionKeys?.length) {
    return [];
  }

  const ordered: string[] = [];
  const seen = new Set<string>();
  for (const rawKey of skillSelectionKeys) {
    const skillKey = rawKey.trim();
    if (!skillKey || seen.has(skillKey)) {
      continue;
    }
    seen.add(skillKey);
    ordered.push(skillKey);
  }
  return ordered;
}

export function normalizeAgentDraftPayload(
  payload: Partial<AgentDraftPayload> | null | undefined,
): AgentDraftFormState {
  return {
    name: payload?.name ?? "",
    description: payload?.description ?? "",
    soul: payload?.soul ?? "",
    skills: orderedUniqueSkillSelectionKeys(payload?.skills),
  };
}

export function toAgentDraftPatchRequest(
  form: AgentDraftFormState,
): AgentDraftPatchRequest {
  return {
    name: form.name,
    description: form.description,
    soul: form.soul,
    skills: orderedUniqueSkillSelectionKeys(form.skills),
  };
}

export function isAgentDraftNameReadonly(mode: AgentDraftMode): boolean {
  return mode === "edit";
}

export function canFinalizeAgentDraft(
  mode: AgentDraftMode,
  form: AgentDraftFormState,
): boolean {
  if (mode === "edit") {
    return true;
  }
  return form.name.trim().length > 0;
}

export function isAgentDraftInputComplete(
  tab: AgentDraftInputTab,
  form: AgentDraftFormState,
): boolean {
  switch (tab) {
    case "name":
      return form.name.trim().length > 0;
    case "description":
      return form.description.trim().length > 0;
    case "soul":
      return form.soul.trim().length > 0;
    case "skills":
      return form.skills.length > 0;
  }
}

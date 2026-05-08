import { withBasePath } from "../config/index.ts";

import type { AgentDraftTab } from "./agent-draft-lifecycle";

const AGENT_DRAFT_TAB_QUERY_KEY = "tab";
const AGENT_DRAFT_TAB_VALUES: AgentDraftTab[] = [
  "name",
  "description",
  "soul",
  "skills",
  "confirm",
];

export function resolveAgentDraftTab(
  value: string | null | undefined,
): AgentDraftTab {
  if (value && AGENT_DRAFT_TAB_VALUES.includes(value as AgentDraftTab)) {
    return value as AgentDraftTab;
  }
  return "name";
}

function withDraftTab(
  currentSearch: string | null | undefined,
  tab?: AgentDraftTab,
): string {
  const params = new URLSearchParams(currentSearch ?? "");
  const resolvedTab = resolveAgentDraftTab(
    tab ?? params.get(AGENT_DRAFT_TAB_QUERY_KEY),
  );
  params.set(AGENT_DRAFT_TAB_QUERY_KEY, resolvedTab);

  const query = params.toString();
  return query ? `?${query}` : "";
}

export function pathOfCreateAgentDraft(options?: {
  currentSearch?: string | null;
  tab?: AgentDraftTab;
}): string {
  return withBasePath(
    `/workspace/agents/new${withDraftTab(options?.currentSearch, options?.tab)}`,
  );
}

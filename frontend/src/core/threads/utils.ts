import type { Message } from "@langchain/langgraph-sdk";

import type { AgentThread } from "./types";

type ThreadRouteRef = {
  thread_id: string;
  metadata?: Record<string, unknown> | null;
  values?: Record<string, unknown> | null;
};
type SearchParamsInput = string | URLSearchParams | null | undefined;

const CHAT_AGENT_QUERY_KEY = "agent";
const CHAT_DRAFT_QUERY_KEY = "draft";

function normalizeAgentName(value: unknown): string | undefined {
  if (typeof value !== "string") {
    return undefined;
  }
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : undefined;
}

function toSearchParams(search: SearchParamsInput): URLSearchParams {
  if (search instanceof URLSearchParams) {
    return new URLSearchParams(search);
  }
  if (typeof search === "string") {
    return new URLSearchParams(
      search.startsWith("?") ? search.slice(1) : search,
    );
  }
  return new URLSearchParams();
}

function buildRoute(pathname: string, searchParams: URLSearchParams): string {
  const query = searchParams.toString();
  return query ? `${pathname}?${query}` : pathname;
}

function getAgentNameFromLegacyThreadPath(
  currentPath: string | undefined,
  threadId: string,
): string | undefined {
  if (currentPath == null) {
    return undefined;
  }

  const match = /^\/workspace\/agents\/([^/]+)\/chats\/([^/]+)$/.exec(
    currentPath,
  );
  if (match?.[2] !== threadId) {
    return undefined;
  }

  return normalizeAgentName(decodeURIComponent(match[1]!));
}

function getAgentNameFromCurrentChatRoute(
  currentPath: string | undefined,
  currentSearch: SearchParamsInput,
  threadId: string,
): string | undefined {
  if (currentPath == null) {
    return undefined;
  }

  const match = /^\/workspace\/chats\/([^/]+)$/.exec(currentPath);
  if (match?.[1] !== threadId) {
    return undefined;
  }

  return normalizeAgentName(
    toSearchParams(currentSearch).get(CHAT_AGENT_QUERY_KEY),
  );
}

export function getThreadAgentName(
  thread: Pick<ThreadRouteRef, "metadata" | "values">,
): string | undefined {
  const metadataAgentName = normalizeAgentName(thread.metadata?.agent_name);
  if (metadataAgentName) {
    return metadataAgentName;
  }

  return normalizeAgentName(thread.values?.agent_name);
}

function buildChatSearchParams(
  currentSearch: SearchParamsInput,
  options: {
    agentName?: string | null;
    hasExplicitAgentName: boolean;
  },
): URLSearchParams {
  const params = toSearchParams(currentSearch);

  if (options.hasExplicitAgentName) {
    const agentName = normalizeAgentName(options.agentName);
    if (agentName) {
      params.set(CHAT_AGENT_QUERY_KEY, agentName);
    } else {
      params.delete(CHAT_AGENT_QUERY_KEY);
    }
  }

  params.delete(CHAT_DRAFT_QUERY_KEY);

  return params;
}

export function currentRouteOf(
  pathname: string,
  currentSearch?: SearchParamsInput,
): string {
  return buildRoute(pathname, toSearchParams(currentSearch));
}

export function pathOfThread(
  thread: ThreadRouteRef | string,
  options?: {
    currentPath?: string;
    currentSearch?: SearchParamsInput;
    agentName?: string | null;
  },
) {
  const threadId = typeof thread === "string" ? thread : thread.thread_id;
  const hasExplicitAgentName = options != null && "agentName" in options;
  const inferredAgentName =
    typeof thread === "string" ? undefined : getThreadAgentName(thread);
  const fallbackAgentName =
    getAgentNameFromLegacyThreadPath(options?.currentPath, threadId) ??
    getAgentNameFromCurrentChatRoute(
      options?.currentPath,
      options?.currentSearch,
      threadId,
    );
  const resolvedAgentName = hasExplicitAgentName
    ? normalizeAgentName(options?.agentName)
    : (inferredAgentName ?? fallbackAgentName);

  const searchParams = buildChatSearchParams(options?.currentSearch, {
    agentName: resolvedAgentName ?? null,
    hasExplicitAgentName: true,
  });

  return buildRoute(`/workspace/chats/${threadId}`, searchParams);
}

export function pathOfNewThread(options?: {
  currentSearch?: SearchParamsInput;
  agentName?: string | null;
}) {
  const hasExplicitAgentName = options != null && "agentName" in options;
  const searchParams = buildChatSearchParams(options?.currentSearch, {
    agentName: options?.agentName ?? null,
    hasExplicitAgentName,
  });

  return buildRoute("/workspace/chats/new", searchParams);
}

export function textOfMessage(message: Message) {
  if (typeof message.content === "string") {
    return message.content;
  } else if (Array.isArray(message.content)) {
    for (const part of message.content) {
      if (part.type === "text") {
        return part.text;
      }
    }
  }
  return null;
}

export function titleOfThread(thread: AgentThread) {
  return thread.values?.title ?? "Untitled";
}

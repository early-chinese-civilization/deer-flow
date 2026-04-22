import type { Message } from "@langchain/langgraph-sdk";

import type { AgentThread } from "./types";

type ThreadRouteRef = Pick<AgentThread, "thread_id" | "metadata" | "values">;

function getThreadAgentName(thread: ThreadRouteRef): string | undefined {
  const metadataAgentName = thread.metadata?.agent_name;
  if (
    typeof metadataAgentName === "string" &&
    metadataAgentName.trim().length > 0
  ) {
    return metadataAgentName;
  }

  const valuesAgentName = thread.values?.agent_name;
  if (
    typeof valuesAgentName === "string" &&
    valuesAgentName.trim().length > 0
  ) {
    return valuesAgentName;
  }

  return undefined;
}

function getAgentNameFromCurrentPath(
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

  return decodeURIComponent(match[1]!);
}

function getAgentNameFromChatNamespace(
  currentPath: string | undefined,
): string | undefined {
  if (currentPath == null) {
    return undefined;
  }

  const match = /^\/workspace\/agents\/([^/]+)\/chats(?:\/[^/]+)?$/.exec(
    currentPath,
  );
  return match?.[1] ? decodeURIComponent(match[1]) : undefined;
}

export function pathOfThread(
  thread: ThreadRouteRef | string,
  options?: { currentPath?: string },
) {
  const threadId = typeof thread === "string" ? thread : thread.thread_id;
  const agentName =
    typeof thread === "string" ? undefined : getThreadAgentName(thread);
  const resolvedAgentName =
    agentName ?? getAgentNameFromCurrentPath(options?.currentPath, threadId);

  if (resolvedAgentName) {
    return `/workspace/agents/${encodeURIComponent(resolvedAgentName)}/chats/${threadId}`;
  }
  return `/workspace/chats/${threadId}`;
}

export function pathOfNewThread(currentPath?: string) {
  const agentName = getAgentNameFromChatNamespace(currentPath);
  if (agentName) {
    return `/workspace/agents/${encodeURIComponent(agentName)}/chats/new`;
  }
  return "/workspace/chats/new";
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

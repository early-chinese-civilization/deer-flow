import type { LocalSettings } from "../settings";

import type { AgentThreadContext } from "./types";

function getAgentName(
  context: LocalSettings["context"],
  extraContext?: Record<string, unknown>,
): string | undefined {
  const contextAgentName = context.agent_name;
  if (typeof contextAgentName === "string" && contextAgentName.trim()) {
    return contextAgentName;
  }

  const extraAgentName = extraContext?.agent_name;
  if (typeof extraAgentName === "string" && extraAgentName.trim()) {
    return extraAgentName;
  }

  return undefined;
}

export function buildThreadSubmitContext(
  threadId: string,
  context: LocalSettings["context"],
  extraContext?: Record<string, unknown>,
): AgentThreadContext {
  const {
    model_name: contextModelName,
    mode: contextMode,
    reasoning_effort: contextReasoningEffort,
    ...restContext
  } = context;
  void [contextModelName, contextMode, contextReasoningEffort];
  const {
    model_name: extraModelName,
    mode: extraMode,
    reasoning_effort: extraReasoningEffort,
    thinking_enabled: extraThinkingEnabled,
    is_plan_mode: extraIsPlanMode,
    subagent_enabled: extraSubagentEnabled,
    thread_id: extraThreadId,
    ...restExtraContext
  } = extraContext ?? {};
  void [
    extraModelName,
    extraMode,
    extraReasoningEffort,
    extraThinkingEnabled,
    extraIsPlanMode,
    extraSubagentEnabled,
    extraThreadId,
  ];

  return {
    ...restExtraContext,
    ...restContext,
    model_name: undefined,
    thinking_enabled: false,
    is_plan_mode: false,
    subagent_enabled: false,
    reasoning_effort: undefined,
    thread_id: threadId,
  };
}

export function buildThreadSubmitMetadata(
  context: LocalSettings["context"],
  extraContext?: Record<string, unknown>,
): Record<string, unknown> | undefined {
  const agentName = getAgentName(context, extraContext);
  if (!agentName) {
    return undefined;
  }
  return {
    agent_name: agentName,
  };
}

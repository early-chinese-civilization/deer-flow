import type { Message, Thread } from "@langchain/langgraph-sdk";

import type { Todo } from "../todos";

export interface AgentThreadState extends Record<string, unknown> {
  title: string;
  messages: Message[];
  artifacts: Record<string, string>;
  todos?: Todo[];
}

export interface AgentThread extends Thread<AgentThreadState> {
  workspace_id?: string | null;
}

export interface ThreadRecord {
  thread_id: string;
  workspace_id: string | null;
  status: string;
  created_at: string;
  updated_at: string;
  metadata: Record<string, unknown>;
  values: Record<string, unknown>;
  interrupts: Record<string, unknown>;
}

export interface AgentThreadContext extends Record<string, unknown> {
  thread_id: string;
  model_name: string | undefined;
  thinking_enabled: boolean;
  is_plan_mode: boolean;
  subagent_enabled: boolean;
  reasoning_effort?: "minimal" | "low" | "medium" | "high";
  agent_name?: string;
}

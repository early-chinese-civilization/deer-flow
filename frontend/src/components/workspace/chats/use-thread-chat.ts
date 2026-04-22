"use client";

import { useParams, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { uuid } from "@/core/utils/uuid";

import {
  promoteThreadChatState,
  resolveThreadChatState,
} from "./thread-chat-state";

export function useThreadChat(options?: {
  draftAgentName?: string | null;
  draftResetKey?: string | null;
}) {
  const { thread_id: threadIdFromPath } = useParams<{ thread_id: string }>();
  const searchParams = useSearchParams();
  const draftAgentName = options?.draftAgentName ?? searchParams.get("agent");
  const draftResetKey = options?.draftResetKey ?? searchParams.get("draft");
  const [threadState, setThreadState] = useState(() =>
    resolveThreadChatState(threadIdFromPath, uuid),
  );

  const commitThreadId = (nextThreadId: string) => {
    setThreadState(promoteThreadChatState(nextThreadId));
  };

  useEffect(() => {
    setThreadState(resolveThreadChatState(threadIdFromPath, uuid));
  }, [draftAgentName, draftResetKey, threadIdFromPath]);
  const isMock = searchParams.get("mock") === "true";
  return {
    threadId: threadState.threadId,
    isNewThread: threadState.isNewThread,
    setIsNewThread: (value: boolean) =>
      setThreadState((current) => ({ ...current, isNewThread: value })),
    commitThreadId,
    isMock,
  };
}

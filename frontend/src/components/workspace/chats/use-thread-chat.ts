"use client";

import { useParams, useSearchParams } from "next/navigation";
import { useRef, useState } from "react";

import { uuid } from "@/core/utils/uuid";

import {
  buildThreadChatRouteKey,
  promoteThreadChatState,
  resolveThreadChatState,
  selectThreadChatState,
  type PromotedThreadChatState,
  type ThreadChatState,
} from "./thread-chat-state";

export function useThreadChat(options?: {
  draftAgentName?: string | null;
  draftResetKey?: string | null;
}) {
  const { thread_id: threadIdFromPath } = useParams<{ thread_id: string }>();
  const searchParams = useSearchParams();
  const draftAgentName = options?.draftAgentName ?? searchParams.get("agent");
  const draftResetKey = options?.draftResetKey ?? searchParams.get("draft");
  const routeKey = buildThreadChatRouteKey({
    threadIdFromPath,
    draftAgentName,
    draftResetKey,
  });
  const routeStatesRef = useRef(new Map<string, ThreadChatState>());
  const routeState = (() => {
    const existing = routeStatesRef.current.get(routeKey);
    if (existing) {
      return existing;
    }

    const nextState = resolveThreadChatState(threadIdFromPath, uuid);
    routeStatesRef.current.set(routeKey, nextState);
    return nextState;
  })();
  const [promoted, setPromoted] = useState<PromotedThreadChatState | null>(
    null,
  );
  const threadState = selectThreadChatState({
    routeKey,
    routeState,
    promoted,
  });

  const commitThreadId = (nextThreadId: string) => {
    setPromoted({
      routeKey,
      state: promoteThreadChatState(nextThreadId),
    });
  };

  const isMock = searchParams.get("mock") === "true";
  return {
    threadId: threadState.threadId,
    isNewThread: threadState.isNewThread,
    setIsNewThread: (value: boolean) =>
      setPromoted({
        routeKey,
        state: { ...threadState, isNewThread: value },
      }),
    commitThreadId,
    isMock,
  };
}

export type ThreadChatState = {
  threadId: string;
  isNewThread: boolean;
};

export type PromotedThreadChatState = {
  routeKey: string;
  state: ThreadChatState;
};

export function buildThreadChatRouteKey(options: {
  threadIdFromPath: string;
  draftAgentName?: string | null;
  draftResetKey?: string | null;
}): string {
  return [
    options.threadIdFromPath,
    options.draftAgentName ?? "",
    options.draftResetKey ?? "",
  ].join("|");
}

export function resolveThreadChatState(
  threadIdFromPath: string,
  createDraftThreadId: () => string,
): ThreadChatState {
  if (threadIdFromPath === "new") {
    return {
      threadId: createDraftThreadId(),
      isNewThread: true,
    };
  }

  return {
    threadId: threadIdFromPath,
    isNewThread: false,
  };
}

export function promoteThreadChatState(threadId: string): ThreadChatState {
  return {
    threadId,
    isNewThread: false,
  };
}

export function selectThreadChatState({
  routeKey,
  routeState,
  promoted,
}: {
  routeKey: string;
  routeState: ThreadChatState;
  promoted: PromotedThreadChatState | null;
}): ThreadChatState {
  if (promoted?.routeKey === routeKey) {
    return promoted.state;
  }
  return routeState;
}

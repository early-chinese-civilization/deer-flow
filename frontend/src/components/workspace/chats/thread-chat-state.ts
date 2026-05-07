export type ThreadChatState = {
  threadId: string;
  isNewThread: boolean;
};

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

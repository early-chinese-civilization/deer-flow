export type TransientArtifactAutoOpenParams = {
  threadId?: string;
  path: string;
  messageId?: string;
  toolCallId?: string;
};

export function buildTransientArtifactAutoOpenId({
  threadId,
  path,
  messageId,
  toolCallId,
}: TransientArtifactAutoOpenParams): string {
  const url = new URL(`write-file:${path}`);
  if (messageId) {
    url.searchParams.set("message_id", messageId);
  }
  if (toolCallId) {
    url.searchParams.set("tool_call_id", toolCallId);
  }
  if (threadId) {
    url.searchParams.set("thread_id", threadId);
  }
  return url.toString();
}

export function createTransientArtifactAutoOpenRegistry(
  initialIds: Iterable<string> = [],
) {
  const openedIds = new Set(initialIds);

  return {
    has(id: string): boolean {
      return openedIds.has(id);
    },
    mark(id: string): void {
      openedIds.add(id);
    },
  };
}

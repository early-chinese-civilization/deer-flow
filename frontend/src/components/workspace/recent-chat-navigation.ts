import type { AgentThread } from "@/core/threads/types";

export function getRouteAfterThreadDelete({
  threads,
  deletedThreadId,
  currentRoute,
  currentThreadId,
  newThreadRoute,
  getThreadRoute,
}: {
  threads: AgentThread[];
  deletedThreadId: string;
  currentRoute: string;
  currentThreadId?: string | null;
  newThreadRoute: string;
  getThreadRoute: (thread: AgentThread) => string;
}): string | null {
  const threadIndex = threads.findIndex(
    (thread) => thread.thread_id === deletedThreadId,
  );
  const deletedThread = threadIndex >= 0 ? threads[threadIndex] : null;
  const deletedThreadRoute = deletedThread
    ? getThreadRoute(deletedThread)
    : null;

  if (
    deletedThreadId !== currentThreadId &&
    deletedThreadRoute !== currentRoute
  ) {
    return null;
  }

  if (threadIndex > -1) {
    const nextThread = threads[threadIndex + 1] ?? threads[threadIndex - 1];
    if (nextThread) {
      return getThreadRoute(nextThread);
    }
  }

  return newThreadRoute;
}

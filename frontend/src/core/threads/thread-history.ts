import type { ThreadState } from "@langchain/langgraph-sdk";

export type ThreadHistoryLimit = false | { limit: number } | undefined;

export function resolveThreadHistoryLimit(
  fetchStateHistory: ThreadHistoryLimit,
): number | false {
  if (typeof fetchStateHistory === "object" && fetchStateHistory !== null) {
    return fetchStateHistory.limit ?? false;
  }
  return fetchStateHistory ?? false;
}

export function getThreadHistoryQueryKey(
  threadId: string | null | undefined,
  historyLimit: number | false,
) {
  return ["threads", "history", threadId ?? null, historyLimit] as const;
}

export type ThreadHistoryClient<StateType> = {
  threads: {
    getState(threadId: string): Promise<ThreadState<StateType>>;
    getHistory(
      threadId: string,
      options: { limit: number },
    ): Promise<ThreadState<StateType>[]>;
  };
};

export async function fetchThreadHistory<StateType>(
  client: ThreadHistoryClient<StateType>,
  threadId: string,
  historyLimit: number | false,
): Promise<ThreadState<StateType>[]> {
  if (historyLimit === false) {
    const state = await client.threads.getState(threadId);
    if (state.checkpoint == null) {
      return [];
    }
    return [state];
  }

  return client.threads.getHistory(threadId, {
    limit: historyLimit,
  });
}

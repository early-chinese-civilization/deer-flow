import type { AIMessage, Message, ThreadState } from "@langchain/langgraph-sdk";
import type { ThreadsClient } from "@langchain/langgraph-sdk/client";
import { useStream } from "@langchain/langgraph-sdk/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import type { PromptInputMessage } from "@/components/ai-elements/prompt-input";

import { getAPIClient } from "../api";
import { getBackendBaseURL } from "../config";
import type { FileInMessage } from "../messages/utils";
import type { LocalSettings } from "../settings";
import { useUpdateSubtask } from "../tasks/context";
import type { UploadedFileInfo } from "../uploads";
import { getCanonicalUploadedFilePath } from "../uploads/composer-core";

import { ensureThread } from "./api";
import {
  applyPendingUploadedFiles,
  type PendingUploadedFiles,
} from "./message-attachments";
import { getRunReconnectStorage } from "./reconnect-storage";
import {
  shouldNotifyThreadStartBeforeEnsureThread,
  shouldShowOptimisticMessageBeforeEnsureThread,
} from "./send-lifecycle";
import { shouldSuppressPassiveStreamError } from "./stream-error";
import { resolveNextStreamThreadId } from "./stream-thread-id";
import {
  buildThreadSubmitContext,
  buildThreadSubmitMetadata,
} from "./submit-context";
import {
  fetchThreadHistory,
  getThreadHistoryQueryKey,
  resolveThreadHistoryLimit,
  type ThreadHistoryClient,
  type ThreadHistoryLimit,
} from "./thread-history";
import type { AgentThread, AgentThreadState } from "./types";

export type ToolEndEvent = {
  name: string;
  data: unknown;
};

export type ThreadStreamOptions = {
  threadId?: string | null | undefined;
  context: LocalSettings["context"];
  isMock?: boolean;
  onStart?: (threadId: string) => void;
  onFinish?: (state: AgentThreadState) => void;
  onToolEnd?: (event: ToolEndEvent) => void;
};

type SendMessageOptions = {
  workspaceId?: string | null;
  uploadedFiles?: UploadedFileInfo[];
};

function getStreamErrorMessage(error: unknown): string {
  if (typeof error === "string" && error.trim()) {
    return error;
  }
  if (error instanceof Error && error.message.trim()) {
    return error.message;
  }
  if (typeof error === "object" && error !== null) {
    const message = Reflect.get(error, "message");
    if (typeof message === "string" && message.trim()) {
      return message;
    }
    const nestedError = Reflect.get(error, "error");
    if (nestedError instanceof Error && nestedError.message.trim()) {
      return nestedError.message;
    }
    if (typeof nestedError === "string" && nestedError.trim()) {
      return nestedError;
    }
  }
  return "Request failed.";
}

function useManagedThreadHistory(
  client: ReturnType<typeof getAPIClient>,
  threadId: string | null | undefined,
  fetchStateHistory: ThreadHistoryLimit,
) {
  const queryClient = useQueryClient();
  const historyLimit = resolveThreadHistoryLimit(fetchStateHistory);

  const fetchHistory = useCallback(
    async (
      targetThreadId: string,
    ): Promise<ThreadState<AgentThreadState>[]> => {
      return fetchThreadHistory<AgentThreadState>(
        client as ThreadHistoryClient<AgentThreadState>,
        targetThreadId,
        historyLimit,
      );
    },
    [client, historyLimit],
  );

  const query = useQuery<ThreadState<AgentThreadState>[]>({
    queryKey: getThreadHistoryQueryKey(threadId, historyLimit),
    queryFn: async () => {
      if (!threadId) {
        return [];
      }
      return fetchHistory(threadId);
    },
    enabled: threadId != null,
    refetchOnWindowFocus: false,
  });

  const mutate = useCallback(
    async (mutateId?: string) => {
      const targetThreadId = mutateId ?? threadId;
      if (!targetThreadId) {
        return undefined;
      }

      return queryClient.fetchQuery<ThreadState<AgentThreadState>[]>({
        queryKey: getThreadHistoryQueryKey(targetThreadId, historyLimit),
        queryFn: () => fetchHistory(targetThreadId),
      });
    },
    [fetchHistory, historyLimit, queryClient, threadId],
  );

  return {
    data: query.data,
    error: query.error,
    isLoading: query.isLoading,
    mutate,
  };
}

export function useThreadStream({
  threadId,
  context,
  isMock,
  onStart,
  onFinish,
  onToolEnd,
}: ThreadStreamOptions) {
  // Track the thread ID that is currently streaming to handle thread changes during streaming
  const [onStreamThreadId, setOnStreamThreadId] = useState(() => threadId);
  // Ref to track current thread ID across async callbacks without causing re-renders,
  // and to allow access to the current thread id in onUpdateEvent
  const threadIdRef = useRef<string | null>(threadId ?? null);
  const startedRef = useRef(false);

  const listeners = useRef({
    onStart,
    onFinish,
    onToolEnd,
  });

  // Keep listeners ref updated with latest callbacks
  useEffect(() => {
    listeners.current = { onStart, onFinish, onToolEnd };
  }, [onStart, onFinish, onToolEnd]);

  useEffect(() => {
    const normalizedThreadId = threadId ?? null;
    const nextOnStreamThreadId = resolveNextStreamThreadId(
      onStreamThreadId,
      normalizedThreadId,
    );
    if (!normalizedThreadId) {
      // Reset for new thread creation when threadId becomes null/undefined.
      startedRef.current = false;
    }
    setOnStreamThreadId(nextOnStreamThreadId);
    threadIdRef.current = normalizedThreadId;
  }, [onStreamThreadId, threadId]);

  const _handleOnStart = useCallback((id: string) => {
    if (!startedRef.current) {
      listeners.current.onStart?.(id);
      startedRef.current = true;
    }
  }, []);

  const handleStreamStart = useCallback(
    (_threadId: string) => {
      threadIdRef.current = _threadId;
      _handleOnStart(_threadId);
    },
    [_handleOnStart],
  );

  const queryClient = useQueryClient();
  const updateSubtask = useUpdateSubtask();
  const sendInFlightRef = useRef(false);
  const client = getAPIClient(isMock);
  const threadHistory = useManagedThreadHistory(client, onStreamThreadId, {
    limit: 1,
  });

  const thread = useStream<AgentThreadState>({
    client,
    assistantId: "lead_agent",
    threadId: onStreamThreadId,
    reconnectOnMount: getRunReconnectStorage,
    fetchStateHistory: { limit: 1 },
    thread: threadHistory,
    onCreated(meta) {
      handleStreamStart(meta.thread_id);
      setOnStreamThreadId(meta.thread_id);
    },
    onLangChainEvent(event) {
      if (event.event === "on_tool_end") {
        listeners.current.onToolEnd?.({
          name: event.name,
          data: event.data,
        });
      }
    },
    onUpdateEvent(data) {
      const updates: Array<Partial<AgentThreadState> | null> = Object.values(
        data || {},
      );
      for (const update of updates) {
        if (update && "title" in update && update.title) {
          void queryClient.setQueriesData(
            {
              queryKey: ["threads", "search"],
              exact: false,
            },
            (oldData: Array<AgentThread> | undefined) => {
              return oldData?.map((t) => {
                if (t.thread_id === threadIdRef.current) {
                  return {
                    ...t,
                    values: {
                      ...t.values,
                      title: update.title,
                    },
                  };
                }
                return t;
              });
            },
          );
        }
      }
    },
    onCustomEvent(event: unknown) {
      if (
        typeof event === "object" &&
        event !== null &&
        "type" in event &&
        event.type === "task_running"
      ) {
        const e = event as {
          type: "task_running";
          task_id: string;
          message: AIMessage;
        };
        updateSubtask({ id: e.task_id, latestMessage: e.message });
        return;
      }

      if (
        typeof event === "object" &&
        event !== null &&
        "type" in event &&
        event.type === "llm_retry" &&
        "message" in event &&
        typeof event.message === "string" &&
        event.message.trim()
      ) {
        const e = event as { type: "llm_retry"; message: string };
        toast(e.message);
      }
    },
    onError(error, run) {
      setOptimisticMessages([]);
      if (
        shouldSuppressPassiveStreamError(run, {
          sendInFlight: sendInFlightRef.current,
        })
      ) {
        return;
      }
      toast.error(getStreamErrorMessage(error));
    },
    onFinish(state) {
      listeners.current.onFinish?.(state.values);
      void queryClient.invalidateQueries({ queryKey: ["threads", "search"] });
    },
  });

  // Optimistic messages shown before the server stream responds
  const [optimisticMessages, setOptimisticMessages] = useState<Message[]>([]);
  const [pendingUploadedFiles, setPendingUploadedFiles] =
    useState<PendingUploadedFiles | null>(null);
  const [isSending, setIsSending] = useState(false);
  // Track message count before sending so we know when server has responded
  const prevMsgCountRef = useRef(thread.messages.length);

  const pendingFilesResult = useMemo(
    () => applyPendingUploadedFiles(thread.messages, pendingUploadedFiles),
    [pendingUploadedFiles, thread.messages],
  );

  // Clear optimistic once the server-side human turn exists in the stream.
  useEffect(() => {
    const hasServerResponse =
      pendingUploadedFiles !== null
        ? pendingFilesResult.hasServerHumanMessage
        : thread.messages.length > prevMsgCountRef.current;

    if (optimisticMessages.length > 0 && hasServerResponse) {
      setOptimisticMessages([]);
    }
  }, [
    optimisticMessages.length,
    pendingFilesResult.hasServerHumanMessage,
    pendingUploadedFiles,
    thread.messages.length,
  ]);

  useEffect(() => {
    if (pendingUploadedFiles && pendingFilesResult.hasPersistedFiles) {
      setPendingUploadedFiles(null);
    }
  }, [pendingFilesResult.hasPersistedFiles, pendingUploadedFiles]);

  const sendMessage = useCallback(
    async (
      threadId: string,
      message: PromptInputMessage,
      extraContext?: Record<string, unknown>,
      options?: SendMessageOptions,
    ): Promise<void> => {
      if (sendInFlightRef.current) {
        return;
      }
      sendInFlightRef.current = true;
      setIsSending(true);

      const text = message.text.trim();
      const uploadedFileInfo = options?.uploadedFiles ?? [];

      // Capture current count before showing optimistic messages
      prevMsgCountRef.current = thread.messages.length;

      const optimisticFiles: FileInMessage[] = uploadedFileInfo.map((info) => ({
        filename: info.filename,
        size: info.size,
        path: getCanonicalUploadedFilePath(info),
        virtual_path: info.virtual_path,
        oss_uri: info.oss_uri,
        object_key: info.object_key,
        status: "uploaded" as const,
      }));

      const newOptimistic: Message[] = [
        {
          type: "human",
          id: `opt-human-${Date.now()}`,
          content: text ? [{ type: "text", text }] : "",
          additional_kwargs:
            optimisticFiles.length > 0 ? { files: optimisticFiles } : {},
        },
      ];

      const shouldEnsureThread = !threadIdRef.current;
      if (shouldShowOptimisticMessageBeforeEnsureThread(!shouldEnsureThread)) {
        setOptimisticMessages(newOptimistic);
      }
      if (shouldNotifyThreadStartBeforeEnsureThread(!shouldEnsureThread)) {
        _handleOnStart(threadId);
      }
      let ensuredThread: Awaited<ReturnType<typeof ensureThread>> | undefined =
        undefined;

      try {
        if (shouldEnsureThread) {
          ensuredThread = await ensureThread(threadId, {
            workspaceId: options?.workspaceId ?? undefined,
          });
          queryClient.setQueryData(
            ["threads", "detail", threadId],
            ensuredThread,
          );
          _handleOnStart(threadId);
          setOptimisticMessages(newOptimistic);
        }

        const filesForSubmit: FileInMessage[] = uploadedFileInfo.map(
          (info) => ({
            filename: info.filename,
            size: info.size,
            path: getCanonicalUploadedFilePath(info),
            virtual_path: info.virtual_path,
            oss_uri: info.oss_uri,
            object_key: info.object_key,
            status: "uploaded" as const,
          }),
        );

        setPendingUploadedFiles(
          filesForSubmit.length > 0
            ? {
                fromIndex: prevMsgCountRef.current,
                files: filesForSubmit,
              }
            : null,
        );

        await thread.submit(
          {
            messages: [
              {
                type: "human",
                content: [
                  {
                    type: "text",
                    text,
                  },
                ],
                additional_kwargs:
                  filesForSubmit.length > 0 ? { files: filesForSubmit } : {},
              },
            ],
          },
          {
            threadId: threadId,
            streamSubgraphs: true,
            streamResumable: true,
            metadata: buildThreadSubmitMetadata(context, extraContext),
            config: {
              recursion_limit: 1000,
            },
            context: buildThreadSubmitContext(threadId, context, extraContext),
          },
        );
        void queryClient.invalidateQueries({ queryKey: ["threads", "search"] });
      } catch (error) {
        setOptimisticMessages([]);
        setPendingUploadedFiles(null);
        throw error;
      } finally {
        sendInFlightRef.current = false;
        setIsSending(false);
      }
    },
    [thread, _handleOnStart, context, queryClient],
  );

  // Merge thread with optimistic messages for display
  const shouldAppendOptimisticMessages =
    optimisticMessages.length > 0 &&
    (!pendingUploadedFiles || !pendingFilesResult.hasServerHumanMessage);

  const mergedThread = shouldAppendOptimisticMessages
    ? ({
        ...thread,
        messages: [...pendingFilesResult.messages, ...optimisticMessages],
      } as typeof thread)
    : ({
        ...thread,
        messages: pendingFilesResult.messages,
      } as typeof thread);

  return [mergedThread, sendMessage, isSending] as const;
}

export function useThreads(
  params: Parameters<ThreadsClient["search"]>[0] = {
    limit: 50,
    sortBy: "updated_at",
    sortOrder: "desc",
    select: ["thread_id", "updated_at", "values", "metadata"],
  },
) {
  const apiClient = getAPIClient();
  return useQuery<AgentThread[]>({
    queryKey: ["threads", "search", params],
    queryFn: async () => {
      const maxResults = params.limit;
      const initialOffset = params.offset ?? 0;
      const DEFAULT_PAGE_SIZE = 50;

      // Preserve prior semantics: if a non-positive limit is explicitly provided,
      // delegate to a single search call with the original parameters.
      if (maxResults !== undefined && maxResults <= 0) {
        const response =
          await apiClient.threads.search<AgentThreadState>(params);
        return response as AgentThread[];
      }

      const pageSize =
        typeof maxResults === "number" && maxResults > 0
          ? Math.min(DEFAULT_PAGE_SIZE, maxResults)
          : DEFAULT_PAGE_SIZE;

      const threads: AgentThread[] = [];
      let offset = initialOffset;

      while (true) {
        if (typeof maxResults === "number" && threads.length >= maxResults) {
          break;
        }

        const currentLimit =
          typeof maxResults === "number"
            ? Math.min(pageSize, maxResults - threads.length)
            : pageSize;

        if (typeof maxResults === "number" && currentLimit <= 0) {
          break;
        }

        const response = (await apiClient.threads.search<AgentThreadState>({
          ...params,
          limit: currentLimit,
          offset,
        })) as AgentThread[];

        threads.push(...response);

        if (response.length < currentLimit) {
          break;
        }

        offset += response.length;
      }

      return threads;
    },
    refetchOnWindowFocus: false,
  });
}

export function useDeleteThread() {
  const queryClient = useQueryClient();
  const apiClient = getAPIClient();
  return useMutation({
    mutationFn: async ({ threadId }: { threadId: string }) => {
      await apiClient.threads.delete(threadId);

      const response = await fetch(
        `${getBackendBaseURL()}/api/threads/${encodeURIComponent(threadId)}`,
        {
          method: "DELETE",
        },
      );

      if (!response.ok) {
        const error = await response
          .json()
          .catch(() => ({ detail: "Failed to delete local thread data." }));
        throw new Error(error.detail ?? "Failed to delete local thread data.");
      }
    },
    onSuccess(_, { threadId }) {
      queryClient.setQueriesData(
        {
          queryKey: ["threads", "search"],
          exact: false,
        },
        (oldData: Array<AgentThread> | undefined) => {
          if (oldData == null) {
            return oldData;
          }
          return oldData.filter((t) => t.thread_id !== threadId);
        },
      );
    },
    onSettled() {
      void queryClient.invalidateQueries({ queryKey: ["threads", "search"] });
    },
  });
}

export function useRenameThread() {
  const queryClient = useQueryClient();
  const apiClient = getAPIClient();
  return useMutation({
    mutationFn: async ({
      threadId,
      title,
    }: {
      threadId: string;
      title: string;
    }) => {
      await apiClient.threads.updateState(threadId, {
        values: { title },
      });
    },
    onSuccess(_, { threadId, title }) {
      queryClient.setQueriesData(
        {
          queryKey: ["threads", "search"],
          exact: false,
        },
        (oldData: Array<AgentThread>) => {
          return oldData.map((t) => {
            if (t.thread_id === threadId) {
              return {
                ...t,
                values: {
                  ...t.values,
                  title,
                },
              };
            }
            return t;
          });
        },
      );
    },
  });
}

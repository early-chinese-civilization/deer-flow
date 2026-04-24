"use client";

import { useQuery } from "@tanstack/react-query";
import { usePathname, useSearchParams } from "next/navigation";
import { parseAsString, useQueryStates } from "nuqs";
import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import type { PromptInputMessage } from "@/components/ai-elements/prompt-input";
import { AgentWelcome } from "@/components/workspace/agent-welcome";
import {
  ChatBox,
  useSpecificChatMode,
  useThreadChat,
} from "@/components/workspace/chats";
import {
  DraftAgentControl,
  ThreadAgentBadge,
} from "@/components/workspace/chats/chat-agent-control";
import { ExportTrigger } from "@/components/workspace/export-trigger";
import { InputBox } from "@/components/workspace/input-box";
import { MessageList } from "@/components/workspace/messages";
import { ThreadContext } from "@/components/workspace/messages/context";
import { ThreadTitle } from "@/components/workspace/thread-title";
import { TodoList } from "@/components/workspace/todo-list";
import { Welcome } from "@/components/workspace/welcome";
import { WorkspaceFilesPanel } from "@/components/workspace/workspace-files-panel";
import { WorkspaceFilesTrigger } from "@/components/workspace/workspace-files-trigger";
import { useAgent, useAgents } from "@/core/agents";
import { useI18n } from "@/core/i18n/hooks";
import { useNotification } from "@/core/notification/hooks";
import { useThreadSettings } from "@/core/settings";
import { getThread } from "@/core/threads/api";
import { useThreadStream } from "@/core/threads/hooks";
import { textOfMessage } from "@/core/threads/utils";
import {
  currentRouteOf,
  getThreadAgentName,
  pathOfThread,
} from "@/core/threads/utils";
import { useComposerAttachmentUploads } from "@/core/uploads/composer";
import { hasBlockingAttachmentUploads } from "@/core/uploads/composer-core";
import { uuid } from "@/core/utils/uuid";
import { env } from "@/env";
import { cn } from "@/lib/utils";

function normalizeQueryValue(value: string | null | undefined): string | null {
  if (typeof value !== "string") {
    return null;
  }
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

const draftQueryParsers = {
  agent: parseAsString,
  draft: parseAsString,
};

export function SharedChatPage({
  initialAgentName,
  initialDraftNonce,
}: {
  initialAgentName?: string;
  initialDraftNonce?: string;
}) {
  const { t } = useI18n();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const searchParamsString = searchParams.toString();
  const [showFilesPanel, setShowFilesPanel] = useState(true);
  const [hasMounted, setHasMounted] = useState(false);
  const [{ agent: draftAgentQuery, draft: draftNonceQuery }, setDraftQuery] =
    useQueryStates(draftQueryParsers, {
      history: "replace",
      shallow: true,
    });

  useEffect(() => {
    setHasMounted(true);
  }, []);

  const draftAgentName = normalizeQueryValue(
    hasMounted ? draftAgentQuery : draftAgentQuery ?? initialAgentName ?? null,
  );
  const draftNonce = normalizeQueryValue(
    hasMounted ? draftNonceQuery : draftNonceQuery ?? initialDraftNonce ?? null,
  );

  const { threadId, isNewThread, commitThreadId, isMock } = useThreadChat({
    draftAgentName,
    draftResetKey: draftNonce,
  });
  useSpecificChatMode(draftNonce ?? draftAgentName ?? undefined);

  const [settings] = useThreadSettings(threadId);
  const { agents, isLoading: agentsLoading } = useAgents();
  const { showNotification } = useNotification();

  const threadDetailQuery = useQuery({
    queryKey: ["threads", "detail", threadId],
    queryFn: () => getThread(threadId),
    enabled: !isNewThread,
    refetchOnWindowFocus: false,
  });

  const persistedAgentName = useMemo(() => {
    if (isNewThread || !threadDetailQuery.data) {
      return undefined;
    }
    return getThreadAgentName(threadDetailQuery.data);
  }, [isNewThread, threadDetailQuery.data]);

  const effectiveAgentName = isNewThread
    ? draftAgentName ?? undefined
    : persistedAgentName;
  const { agent } = useAgent(effectiveAgentName);

  const submitContext = useMemo(() => {
    if (!effectiveAgentName) {
      return settings.context;
    }
    return {
      ...settings.context,
      agent_name: effectiveAgentName,
    };
  }, [effectiveAgentName, settings.context]);

  const persistedWorkspaceId = threadDetailQuery.data?.workspace_id ?? null;
  const { composerWorkspaceId } = useComposerAttachmentUploads({
    persistedWorkspaceId,
  });

  const [thread, sendMessage, isSendingMessage] = useThreadStream({
    threadId: isNewThread ? undefined : threadId,
    context: submitContext,
    isMock,
    onStart: (resolvedThreadId) => {
      commitThreadId(resolvedThreadId);
      history.replaceState(
        null,
        "",
        pathOfThread(resolvedThreadId, {
          currentPath: pathname,
          currentSearch: searchParamsString,
          agentName: effectiveAgentName ?? null,
        }),
      );
    },
    onFinish: (state) => {
      if (document.hidden || !document.hasFocus()) {
        let body = "Conversation finished";
        const lastMessage = state.messages.at(-1);
        if (lastMessage) {
          const textContent = textOfMessage(lastMessage);
          if (textContent) {
            body =
              textContent.length > 200
                ? textContent.substring(0, 200) + "..."
                : textContent;
          }
        }
        showNotification(state.title, { body });
      }
    },
  });

  useEffect(() => {
    if (isNewThread || !threadDetailQuery.data) {
      return;
    }

    const canonicalRoute = pathOfThread(threadDetailQuery.data, {
      currentPath: pathname,
      currentSearch: searchParamsString,
    });
    const currentRoute = currentRouteOf(pathname, searchParamsString);

    if (canonicalRoute !== currentRoute) {
      history.replaceState(null, "", canonicalRoute);
    }
  }, [isNewThread, pathname, searchParamsString, threadDetailQuery.data]);

  const handleDraftAgentChange = useCallback(
    (nextAgentName: string | null) => {
      void setDraftQuery({
        agent: nextAgentName,
        draft: uuid(),
      });
    },
    [setDraftQuery],
  );

  const handleSubmit = useCallback(
    (message: PromptInputMessage) => {
      if (!isNewThread && !threadDetailQuery.isSuccess) {
        return;
      }
      if (hasBlockingAttachmentUploads(message.files)) {
        toast.error(t.uploads.sendBlocked);
        return;
      }

      void sendMessage(
        threadId,
        message,
        effectiveAgentName ? { agent_name: effectiveAgentName } : undefined,
        {
          workspaceId: composerWorkspaceId,
          uploadedFiles: message.files
            .map((file) => file.uploadedFile)
            .filter((file) => file != null),
        },
      );
    },
    [
      composerWorkspaceId,
      effectiveAgentName,
      isNewThread,
      sendMessage,
      t.uploads.sendBlocked,
      threadDetailQuery.isSuccess,
      threadId,
    ],
  );

  const handleStop = useCallback(async () => {
    await thread.stop();
  }, [thread]);

  const agentControl = useMemo(() => {
    if (isNewThread) {
      return (
        <DraftAgentControl
          agentName={draftAgentName}
          agents={agents}
          disabled={thread.isLoading}
          isLoading={agentsLoading}
          onSelectAgent={handleDraftAgentChange}
        />
      );
    }

    if (threadDetailQuery.isPending) {
      return <ThreadAgentBadge isLoading />;
    }

    if (!effectiveAgentName) {
      return null;
    }

    return <ThreadAgentBadge agentName={agent?.name ?? effectiveAgentName} />;
  }, [
    agent?.name,
    agents,
    agentsLoading,
    draftAgentName,
    effectiveAgentName,
    handleDraftAgentChange,
    isNewThread,
    thread.isLoading,
    threadDetailQuery.isPending,
  ]);

  const inputHeader = isNewThread ? (
    draftAgentName ? (
      <AgentWelcome agent={agent} agentName={draftAgentName} />
    ) : (
      <Welcome />
    )
  ) : undefined;

  const inputDisabled =
    env.NEXT_PUBLIC_STATIC_WEBSITE_ONLY === "true" ||
    isSendingMessage ||
    (!isNewThread && !threadDetailQuery.isSuccess);

  return (
    <ThreadContext.Provider value={{ thread, isMock }}>
      <div className="flex size-full min-h-0 overflow-hidden">
        <div className="min-w-0 flex-1">
          <ChatBox threadId={threadId}>
            <div className="relative flex size-full min-h-0 justify-between">
              <header
                className={cn(
                  "absolute top-0 right-0 left-0 z-30 flex h-12 shrink-0 items-center px-4",
                  isNewThread
                    ? "bg-background/0 backdrop-blur-none"
                    : "bg-background/80 shadow-xs backdrop-blur",
                )}
              >
                <div className="flex w-full items-center text-sm font-medium">
                  <ThreadTitle
                    threadId={threadId}
                    thread={thread}
                    isNewThread={isNewThread}
                  />
                </div>
                <div className="flex items-center gap-2">
                  <ExportTrigger threadId={threadId} />
                  {!isNewThread && (
                    <WorkspaceFilesTrigger
                      onClick={() => setShowFilesPanel(true)}
                    />
                  )}
                </div>
              </header>
              <main className="flex min-h-0 max-w-full grow flex-col">
                <div className="flex size-full justify-center">
                  <MessageList
                    className={cn("size-full", !isNewThread && "pt-10")}
                    threadId={threadId}
                    thread={thread}
                  />
                </div>
                <div className="absolute right-0 bottom-0 left-0 z-30 flex justify-center px-4">
                  <div
                    className={cn(
                      "relative w-full",
                      isNewThread && "-translate-y-[calc(50vh-96px)]",
                      isNewThread
                        ? "max-w-(--container-width-sm)"
                        : "max-w-(--container-width-md)",
                    )}
                  >
                    <div className="absolute -top-4 right-0 left-0 z-0">
                      <div className="absolute right-0 bottom-0 left-0">
                        <TodoList
                          className="bg-background/5"
                          todos={thread.values.todos ?? []}
                          hidden={
                            !thread.values.todos ||
                            thread.values.todos.length === 0
                          }
                        />
                      </div>
                    </div>
                    <InputBox
                      key={threadId}
                      className={cn("bg-background/5 w-full -translate-y-4")}
                      isNewThread={isNewThread}
                      threadId={threadId}
                      autoFocus={isNewThread}
                      status={
                        thread.error
                          ? "error"
                          : thread.isLoading
                            ? "streaming"
                            : "ready"
                      }
                      extraHeader={inputHeader}
                      agentControl={agentControl}
                      disabled={inputDisabled}
                      onSubmit={handleSubmit}
                      onStop={handleStop}
                    />
                    {env.NEXT_PUBLIC_STATIC_WEBSITE_ONLY === "true" && (
                      <div className="text-muted-foreground/67 w-full translate-y-12 text-center text-xs">
                        {t.common.notAvailableInDemoMode}
                      </div>
                    )}
                  </div>
                </div>
              </main>
            </div>
          </ChatBox>
        </div>
        {!isNewThread && showFilesPanel && (
          <WorkspaceFilesPanel
            threadId={threadId}
            className="w-[clamp(320px,22vw,420px)] shrink-0"
            onClose={() => setShowFilesPanel(false)}
          />
        )}
      </div>
    </ThreadContext.Provider>
  );
}

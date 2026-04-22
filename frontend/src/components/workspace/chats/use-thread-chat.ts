"use client";

import { useParams, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { uuid } from "@/core/utils/uuid";

export function useThreadChat(options?: {
  draftAgentName?: string | null;
  draftResetKey?: string | null;
}) {
  const { thread_id: threadIdFromPath } = useParams<{ thread_id: string }>();
  const searchParams = useSearchParams();
  const draftAgentName = options?.draftAgentName ?? searchParams.get("agent");
  const draftResetKey = options?.draftResetKey ?? searchParams.get("draft");
  const [threadId, setThreadId] = useState(() => {
    return threadIdFromPath === "new" ? uuid() : threadIdFromPath;
  });

  const [isNewThread, setIsNewThread] = useState(
    () => threadIdFromPath === "new",
  );

  useEffect(() => {
    if (threadIdFromPath === "new") {
      setIsNewThread(true);
      setThreadId(uuid());
      return;
    }

    setIsNewThread(false);
    setThreadId(threadIdFromPath);
  }, [draftAgentName, draftResetKey, threadIdFromPath]);
  const isMock = searchParams.get("mock") === "true";
  return { threadId, isNewThread, setIsNewThread, isMock };
}

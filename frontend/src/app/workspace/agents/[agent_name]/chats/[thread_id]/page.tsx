import { redirect } from "next/navigation";

import { pathOfNewThread, pathOfThread } from "@/core/threads/utils";
import { uuid } from "@/core/utils/uuid";

type LegacyAgentChatPageProps = {
  params: Promise<{
    agent_name: string;
    thread_id: string;
  }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

function toSearchParamsString(
  searchParams: Record<string, string | string[] | undefined>,
): string {
  const nextSearchParams = new URLSearchParams();

  for (const [key, value] of Object.entries(searchParams)) {
    if (Array.isArray(value)) {
      for (const entry of value) {
        nextSearchParams.append(key, entry);
      }
      continue;
    }

    if (typeof value === "string") {
      nextSearchParams.set(key, value);
    }
  }

  return nextSearchParams.toString();
}

export default async function LegacyAgentChatPage({
  params,
  searchParams,
}: LegacyAgentChatPageProps) {
  const [{ agent_name: agentName, thread_id: threadId }, legacySearchParams] =
    await Promise.all([params, searchParams]);
  const currentSearch = toSearchParamsString(legacySearchParams);

  if (threadId === "new") {
    return redirect(
      pathOfNewThread({
        currentSearch,
        agentName,
        draftNonce: uuid(),
      }),
    );
  }

  return redirect(
    pathOfThread(threadId, {
      currentSearch,
      agentName,
    }),
  );
}

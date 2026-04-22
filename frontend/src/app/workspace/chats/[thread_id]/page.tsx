import { SharedChatPage } from "@/components/workspace/chats/shared-chat-page";

type ChatPageProps = {
  params: Promise<{
    thread_id: string;
  }>;
  searchParams: Promise<{
    agent?: string | string[];
    draft?: string | string[];
  }>;
};

function normalizeQueryValue(
  value: string | string[] | undefined,
): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

export default async function ChatPage({ searchParams }: ChatPageProps) {
  const params = await searchParams;

  return (
    <SharedChatPage
      initialAgentName={normalizeQueryValue(params.agent)}
      initialDraftNonce={normalizeQueryValue(params.draft)}
    />
  );
}

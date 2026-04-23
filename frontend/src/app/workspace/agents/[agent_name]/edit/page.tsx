import { AgentDraftFlow } from "@/components/workspace/agents/agent-draft-flow";

interface EditAgentPageProps {
  params: Promise<{
    agent_name: string;
  }>;
}

export default async function EditAgentPage({ params }: EditAgentPageProps) {
  const { agent_name: agentName } = await params;
  return <AgentDraftFlow mode="edit" agentName={agentName} />;
}

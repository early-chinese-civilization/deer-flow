"use client";

import { BotIcon, CheckIcon, ChevronDownIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import type { Agent } from "@/core/agents/types";
import { useI18n } from "@/core/i18n/hooks";
import { cn } from "@/lib/utils";

type AgentOption = Pick<Agent, "name" | "description">;

export function DraftAgentControl({
  agentName,
  agents,
  disabled,
  isLoading,
  onSelectAgent,
}: {
  agentName: string | null;
  agents: AgentOption[];
  disabled?: boolean;
  isLoading?: boolean;
  onSelectAgent: (agentName: string | null) => void;
}) {
  const { t } = useI18n();

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={disabled}
          className="text-muted-foreground min-w-28 w-fit justify-between gap-2 rounded-full px-4 text-xs font-normal transition-colors hover:bg-accent hover:text-accent-foreground"
        >
          <BotIcon className="size-4" />
          <span className="truncate">{agentName ?? t.agents.noAgent}</span>
          <ChevronDownIcon className="size-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" side="top" className="w-64">
        <DropdownMenuItem onSelect={() => onSelectAgent(null)}>
          <div className="flex min-w-0 flex-1 items-center gap-2">
            <BotIcon className="size-4" />
            <span className="truncate">{t.agents.noAgent}</span>
          </div>
          {!agentName && <CheckIcon className="size-4" />}
        </DropdownMenuItem>
        {agents.map((agent) => {
          const isSelected = agent.name === agentName;

          return (
            <DropdownMenuItem
              key={agent.name}
              onSelect={() => onSelectAgent(agent.name)}
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <BotIcon className="size-4" />
                  <span className="truncate">{agent.name}</span>
                </div>
                {agent.description && (
                  <div className="text-muted-foreground truncate pt-1 text-xs">
                    {agent.description}
                  </div>
                )}
              </div>
              {isSelected && <CheckIcon className="size-4" />}
            </DropdownMenuItem>
          );
        })}
        {isLoading && agents.length === 0 && (
          <div className="text-muted-foreground px-2 py-2 text-xs">
            {t.agents.loadingAgent}
          </div>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export function ThreadAgentBadge({
  agentName,
  isLoading,
}: {
  agentName?: string | null;
  isLoading?: boolean;
}) {
  const { t } = useI18n();
  const label = isLoading ? t.agents.loadingAgent : agentName;

  if (!label) {
    return null;
  }

  return (
    <div
      className={cn(
        "bg-background/80 text-muted-foreground flex items-center gap-2 rounded-full border px-4 py-2 text-xs font-medium backdrop-blur-sm",
        !isLoading && "border-primary/30 text-foreground",
      )}
    >
      <BotIcon className="size-4" />
      <span>{label}</span>
    </div>
  );
}

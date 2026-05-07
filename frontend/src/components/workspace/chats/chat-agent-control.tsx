"use client";

import {
  AlertTriangleIcon,
  BotIcon,
  CheckIcon,
  ChevronDownIcon,
  SparklesIcon,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  getMetadataDisplaySummary,
  getMetadataSelectionKey,
  type AgentSkillSourceLabels,
} from "@/core/agents/skill-selection";
import type { Agent, AgentSkillMetadata } from "@/core/agents/types";
import { useI18n } from "@/core/i18n/hooks";
import { isAgentSkillBindingUnavailable } from "@/core/skills/display";
import { cn } from "@/lib/utils";

type AgentOption = Pick<Agent, "name" | "description" | "skill_metadata">;

function AgentSkillSummary({
  skills,
}: {
  skills: AgentSkillMetadata[] | null | undefined;
}) {
  const { t } = useI18n();
  const visibleSkills = skills ?? [];
  const labels: AgentSkillSourceLabels & { unavailableVersion: string } = {
    skillhub: t.agents.skillSourceSkillHub,
    mySkills: t.agents.skillSourceMySkills,
    official: t.agents.skillSourceOfficial,
    unknown: t.agents.skillSourceUnknown,
    unavailableVersion: t.agents.skillVersionUnavailable,
  };

  if (visibleSkills.length === 0) {
    return (
      <div className="text-muted-foreground px-2 py-2 text-xs">
        {t.agents.noBoundSkills}
      </div>
    );
  }

  return (
    <div className="space-y-1 px-2 py-2">
      {visibleSkills.map((skill) => {
        const summary = getMetadataDisplaySummary(skill, labels);
        return (
          <div key={getMetadataSelectionKey(skill)}>
            <div className="flex min-w-0 items-center gap-2 text-xs">
              <SparklesIcon className="text-muted-foreground size-3.5 shrink-0" />
              <span className="truncate font-medium">{summary.name}</span>
              {summary.unavailable && (
                <AlertTriangleIcon className="text-destructive size-3.5 shrink-0" />
              )}
            </div>
            <div
              className={cn(
                "text-muted-foreground mt-0.5 flex flex-wrap gap-2 pl-5 text-xs",
                summary.unavailable && "text-destructive",
              )}
            >
              <span>{summary.versionLabel}</span>
              <span>{summary.sourceLabel}</span>
              {summary.updateAvailable && (
                <span className="text-primary">
                  {t.agents.skillUpdateAvailable}
                </span>
              )}
              {summary.unavailable && (
                <span>{t.agents.skillMetadataUnavailable}</span>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

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
          className="text-muted-foreground hover:bg-accent hover:text-accent-foreground w-fit min-w-28 justify-between gap-2 rounded-full px-4 text-xs font-normal transition-colors"
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
                {agent.skill_metadata && agent.skill_metadata.length > 0 && (
                  <div className="text-muted-foreground truncate pt-1 text-xs">
                    {agent.skill_metadata.length} {t.agents.enabledSkillsLabel}
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
  agent,
  agentName,
  isLoading,
}: {
  agent?: Agent | null;
  agentName?: string | null;
  isLoading?: boolean;
}) {
  const { t } = useI18n();
  const label = isLoading ? t.agents.loadingAgent : agentName;
  const skills = agent?.skill_metadata ?? [];
  const unavailable = skills.some((skill) =>
    isAgentSkillBindingUnavailable(skill),
  );

  if (!label) {
    return null;
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          className={cn(
            "bg-background/80 text-muted-foreground flex items-center gap-2 rounded-full border px-4 py-2 text-xs font-medium backdrop-blur-sm",
            !isLoading && "border-primary/30 text-foreground",
            unavailable && "border-destructive/50",
          )}
        >
          <BotIcon className="size-4" />
          <span>{label}</span>
          {!isLoading && skills.length > 0 && (
            <span className="text-muted-foreground">
              {skills.length} {t.agents.enabledSkillsLabel}
            </span>
          )}
          {unavailable && (
            <AlertTriangleIcon className="text-destructive size-4" />
          )}
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" side="top" className="w-72">
        <div className="border-b px-2 py-2 text-xs font-medium">{label}</div>
        <AgentSkillSummary skills={skills} />
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

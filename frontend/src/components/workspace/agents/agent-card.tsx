"use client";

import {
  BotIcon,
  MessageSquareIcon,
  PencilIcon,
  Trash2Icon,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useDeleteAgent } from "@/core/agents";
import type { Agent } from "@/core/agents";
import { useI18n } from "@/core/i18n/hooks";
import { pathOfNewThread } from "@/core/threads/utils";
import { uuid } from "@/core/utils/uuid";

interface AgentCardProps {
  agent: Agent;
}

export function AgentCard({ agent }: AgentCardProps) {
  const { t } = useI18n();
  const router = useRouter();
  const deleteAgent = useDeleteAgent();
  const [deleteOpen, setDeleteOpen] = useState(false);
  const skills = agent.skills ?? [];
  const visibleSkills = skills.slice(0, 3);
  const hiddenSkillCount = skills.length - visibleSkills.length;

  function handleChat() {
    router.push(
      pathOfNewThread({
        agentName: agent.name,
        draftNonce: uuid(),
      }),
    );
  }

  function handleEdit() {
    router.push(`/workspace/agents/${agent.name}/edit`);
  }

  async function handleDelete() {
    try {
      await deleteAgent.mutateAsync(agent.name);
      toast.success(t.agents.deleteSuccess);
      setDeleteOpen(false);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <>
      <Card className="border-border/60 bg-card hover:border-border py-0 shadow-none transition-colors">
        <div className="flex h-full flex-col">
          <div className="px-5 pt-5">
            <div className="flex items-start justify-between gap-3">
              <div className="flex min-w-0 items-start gap-3">
                <div className="bg-muted text-primary flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border">
                  <BotIcon className="h-5 w-5" />
                </div>
                <div className="min-w-0 space-y-1.5 pt-0.5">
                  <div className="truncate text-base font-semibold tracking-tight">
                    {agent.name}
                  </div>
                  {agent.description && (
                    <div className="text-muted-foreground line-clamp-2 min-h-[2.75rem] text-sm leading-5.5">
                      {agent.description}
                    </div>
                  )}
                </div>
              </div>

              <div className="border-border/70 flex shrink-0 items-center gap-1 rounded-full border p-1">
                <Button
                  size="icon"
                  variant="ghost"
                  className="text-muted-foreground hover:text-foreground h-8 w-8 rounded-full"
                  onClick={handleEdit}
                  title={t.common.edit}
                >
                  <PencilIcon className="h-3.5 w-3.5" />
                </Button>
                <Button
                  size="icon"
                  variant="ghost"
                  className="text-destructive/80 hover:text-destructive h-8 w-8 rounded-full"
                  onClick={() => setDeleteOpen(true)}
                  title={t.agents.delete}
                >
                  <Trash2Icon className="h-3.5 w-3.5" />
                </Button>
              </div>
            </div>
          </div>

          {skills.length > 0 && (
            <div className="px-5 pt-2">
              <div className="flex flex-wrap gap-2">
                {visibleSkills.map((skill) => (
                  <Badge
                    key={skill}
                    variant="outline"
                    className="border-border/60 bg-muted/30 text-foreground rounded-md px-2 py-1 text-[11px] font-medium"
                  >
                    <span className="max-w-[180px] truncate">{skill}</span>
                  </Badge>
                ))}
                {hiddenSkillCount > 0 && (
                  <Badge
                    variant="outline"
                    className="border-border/60 bg-muted/20 text-muted-foreground rounded-md border-dashed px-2 py-1 text-[11px] font-medium"
                  >
                    +{hiddenSkillCount}
                  </Badge>
                )}
              </div>
            </div>
          )}

          <div className="mt-auto px-5 pt-4 pb-5">
            <Button
              size="sm"
              className="h-10 w-full rounded-xl"
              onClick={handleChat}
            >
              <MessageSquareIcon className="mr-1.5 h-3.5 w-3.5" />
              {t.agents.chat}
            </Button>
          </div>
        </div>
      </Card>

      {/* Delete Confirm */}
      <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t.agents.delete}</DialogTitle>
            <DialogDescription>{t.agents.deleteConfirm}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setDeleteOpen(false)}
              disabled={deleteAgent.isPending}
            >
              {t.common.cancel}
            </Button>
            <Button
              variant="destructive"
              onClick={handleDelete}
              disabled={deleteAgent.isPending}
            >
              {deleteAgent.isPending ? t.common.loading : t.common.delete}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

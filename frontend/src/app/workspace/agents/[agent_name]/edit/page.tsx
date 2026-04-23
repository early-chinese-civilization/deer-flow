"use client";

import {
  AlignLeftIcon,
  ArrowLeftIcon,
  BotIcon,
  CheckIcon,
  FileTextIcon,
  SparklesIcon,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Item,
  ItemActions,
  ItemContent,
  ItemDescription,
  ItemTitle,
} from "@/components/ui/item";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Textarea } from "@/components/ui/textarea";
import { useAgent, useUpdateAgent } from "@/core/agents";
import { useI18n } from "@/core/i18n/hooks";
import { useSkills } from "@/core/skills/hooks";
import { cn } from "@/lib/utils";

type EditSection = "name" | "description" | "soul" | "skills";

type FormState = {
  name: string;
  description: string;
  soul: string;
  skills: string[];
};

interface EditAgentPageProps {
  params: Promise<{
    agent_name: string;
  }>;
}

export default function EditAgentPage({ params }: EditAgentPageProps) {
  const { t } = useI18n();
  const router = useRouter();
  const updateAgent = useUpdateAgent();
  const { skills, isLoading: skillsLoading } = useSkills();

  const [agentName, setAgentName] = useState<string | null>(null);
  useEffect(() => {
    let mounted = true;
    void params.then(({ agent_name }) => {
      if (mounted) {
        setAgentName(agent_name);
      }
    });
    return () => {
      mounted = false;
    };
  }, [params]);

  const { agent, isLoading: agentLoading, error: agentError } = useAgent(agentName);

  const [activeSection, setActiveSection] = useState<EditSection>("name");
  const [form, setForm] = useState<FormState>({
    name: "",
    description: "",
    soul: "",
    skills: [],
  });
  const [submitError, setSubmitError] = useState("");
  const [isInitialized, setIsInitialized] = useState(false);

  useEffect(() => {
    if (!agent || isInitialized) {
      return;
    }

    setForm({
      name: agent.name,
      description: agent.description ?? "",
      soul: agent.soul ?? "",
      skills: agent.skills ?? [],
    });
    setIsInitialized(true);
  }, [agent, isInitialized]);

  const sections = useMemo(
    () => [
      {
        id: "name" as const,
        label: t.agents.createSectionName,
        icon: BotIcon,
      },
      {
        id: "description" as const,
        label: t.agents.createSectionDescription,
        icon: AlignLeftIcon,
      },
      {
        id: "soul" as const,
        label: t.agents.createSectionSoul,
        icon: FileTextIcon,
      },
      {
        id: "skills" as const,
        label: t.agents.createSectionSkills,
        icon: SparklesIcon,
      },
    ],
    [
      t.agents.createSectionDescription,
      t.agents.createSectionName,
      t.agents.createSectionSkills,
      t.agents.createSectionSoul,
    ],
  );

  const visibleSkills = useMemo(
    () =>
      skills
        .filter((skill) => skill.category === "custom")
        .sort((left, right) => {
          if (left.category !== right.category) {
            return left.category.localeCompare(right.category);
          }
          return left.name.localeCompare(right.name);
        }),
    [skills],
  );

  function updateField<K extends keyof FormState>(field: K, value: FormState[K]) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  function toggleSkill(skillName: string) {
    setForm((current) => {
      if (current.skills.includes(skillName)) {
        return {
          ...current,
          skills: current.skills.filter((name) => name !== skillName),
        };
      }
      return {
        ...current,
        skills: [...current.skills, skillName],
      };
    });
  }

  async function handleSubmit(options?: { silent?: boolean; navigateBack?: boolean }) {
    if (!agentName) {
      return;
    }

    setSubmitError("");
    try {
      await updateAgent.mutateAsync({
        name: agentName,
        request: {
          description: form.description.trim(),
          soul: form.soul.trim(),
          skills: form.skills,
        },
      });
      if (!options?.silent) {
        toast.success(t.agents.updateSuccess);
      }
      if (options?.navigateBack) {
        router.push("/workspace/agents");
      }
    } catch (error) {
      const message =
        error instanceof Error && error.message ? error.message : t.agents.updateError;
      setSubmitError(message);
      toast.error(message);
    }
  }

  const isDirty = useMemo(() => {
    if (!agent || !isInitialized) return false;
    return (
      form.description.trim() !== (agent.description ?? "").trim() ||
      form.soul.trim() !== (agent.soul ?? "").trim() ||
      JSON.stringify(form.skills.sort()) !== JSON.stringify((agent.skills ?? []).sort())
    );
  }, [agent, isInitialized, form]);

  const submitDisabled =
    updateAgent.isPending ||
    agentLoading ||
    !!agentError ||
    !agentName ||
    !isInitialized ||
    !isDirty;

  const currentPanel = (() => {
    if (activeSection === "name") {
      return (
        <div className="space-y-4">
          <div className="space-y-2">
            <h2 className="text-2xl font-semibold">{t.agents.createNameTitle}</h2>
            <p className="text-muted-foreground text-sm">{t.agents.editNameHint}</p>
          </div>
          <div className="space-y-3">
            <Input
              autoFocus
              value={form.name}
              readOnly
              disabled
            />
          </div>
        </div>
      );
    }

    if (activeSection === "description") {
      return (
        <div className="space-y-4">
          <div className="space-y-2">
            <h2 className="text-2xl font-semibold">{t.agents.createDescriptionTitle}</h2>
            <p className="text-muted-foreground text-sm">
              {t.agents.createDescriptionHint}
            </p>
          </div>
          <Textarea
            autoFocus
            value={form.description}
            onChange={(event) => updateField("description", event.target.value)}
            placeholder={t.agents.description}
            className="min-h-36"
          />
        </div>
      );
    }

    if (activeSection === "soul") {
      return (
        <div className="space-y-4">
          <div className="space-y-2">
            <h2 className="text-2xl font-semibold">{t.agents.createSoulTitle}</h2>
            <p className="text-muted-foreground text-sm">{t.agents.createSoulHint}</p>
          </div>
          <Textarea
            autoFocus
            value={form.soul}
            onChange={(event) => updateField("soul", event.target.value)}
            placeholder="You are..."
            className="min-h-72"
          />
        </div>
      );
    }

    return (
      <div className="space-y-4">
        <div className="space-y-2">
          <h2 className="text-2xl font-semibold">{t.agents.createSkillsTitle}</h2>
          <p className="text-muted-foreground text-sm">{t.agents.createSkillsHint}</p>
        </div>
        <div className="space-y-3">
          {skillsLoading ? (
            <div className="text-muted-foreground text-sm">{t.agents.createSkillsLoading}</div>
          ) : visibleSkills.length === 0 ? (
            <div className="text-muted-foreground text-sm">{t.agents.createSkillsEmpty}</div>
          ) : (
            visibleSkills.map((skill) => {
              const checked = form.skills.includes(skill.name);
              return (
                <button
                  key={skill.name}
                  type="button"
                  onClick={() => toggleSkill(skill.name)}
                  className="block w-full text-left"
                >
                  <Item
                    variant="outline"
                    className={cn(
                      "w-full cursor-pointer justify-between",
                      checked && "border-primary bg-primary/5",
                    )}
                  >
                    <ItemContent>
                      <ItemTitle>{skill.name}</ItemTitle>
                      <ItemDescription>{skill.description}</ItemDescription>
                    </ItemContent>
                    <ItemActions>
                      <div
                        className={cn(
                          "flex h-5 w-5 items-center justify-center rounded border",
                          checked
                            ? "border-primary bg-primary text-primary-foreground"
                            : "border-muted-foreground/40",
                        )}
                      >
                        {checked && <CheckIcon className="h-3.5 w-3.5" />}
                      </div>
                    </ItemActions>
                  </Item>
                </button>
              );
            })
          )}
        </div>
      </div>
    );
  })();

  let content = currentPanel;
  if (agentLoading) {
    content = <div className="text-muted-foreground text-sm">{t.common.loading}</div>;
  } else if (agentError) {
    content = (
      <div className="text-destructive text-sm">
        {agentError instanceof Error ? agentError.message : t.agents.updateError}
      </div>
    );
  }

  return (
    <div className="flex size-full flex-col">
      <header className="flex shrink-0 items-center justify-between gap-3 border-b px-4 py-3">
        <div className="flex items-center gap-3">
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={() => router.push("/workspace/agents")}
          >
            <ArrowLeftIcon className="h-4 w-4" />
          </Button>
          <div>
            <h1 className="text-sm font-semibold">{t.agents.editPageTitle}</h1>
            <p className="text-muted-foreground text-sm">
              {t.agents.editPageDescription}
            </p>
          </div>
        </div>
      </header>

      <main className="grid min-h-0 flex-1 gap-4 p-4 md:grid-cols-[220px_1fr]">
        <nav className="bg-sidebar min-h-0 overflow-y-auto rounded-lg border p-2">
          <ul className="space-y-1 pr-1">
            {sections.map(({ id, label, icon: Icon }) => {
              const active = activeSection === id;
              return (
                <li key={id}>
                  <button
                    type="button"
                    onClick={() => setActiveSection(id)}
                    className={cn(
                      "flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                      active
                        ? "bg-primary text-primary-foreground shadow-sm"
                        : "text-muted-foreground hover:bg-muted hover:text-foreground",
                    )}
                  >
                    <Icon className="size-4" />
                    <span>{label}</span>
                  </button>
                </li>
              );
            })}
          </ul>
        </nav>

        <ScrollArea className="h-full min-h-0 rounded-lg border">
          <div className="space-y-8 p-6">
            <div className="mx-auto w-full max-w-3xl space-y-6">
              <div className="bg-primary/10 flex h-14 w-14 items-center justify-center rounded-full">
                <BotIcon className="text-primary h-7 w-7" />
              </div>

              {content}

              {submitError && (
                <p className="text-destructive text-sm">{submitError}</p>
              )}

              {activeSection !== "name" && (
                <div className="flex items-center justify-end gap-3">
                  <Button
                    variant="outline"
                    onClick={() => router.push("/workspace/agents")}
                    disabled={updateAgent.isPending}
                  >
                    {t.common.cancel}
                  </Button>
                  <Button onClick={() => void handleSubmit()} disabled={submitDisabled}>
                    {updateAgent.isPending
                      ? t.agents.updateButtonPending
                      : t.agents.updateButton}
                  </Button>
                </div>
              )}
            </div>
          </div>
        </ScrollArea>
      </main>
    </div>
  );
}

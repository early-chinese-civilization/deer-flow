"use client";

import {
  AlignLeftIcon,
  ArrowLeftIcon,
  BotIcon,
  CheckCircle2Icon,
  CheckIcon,
  FileTextIcon,
  SparklesIcon,
} from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { useAgent, useCreateAgent, useUpdateAgent } from "@/core/agents";
import {
  canFinalizeAgentDraft,
  isAgentDraftNameReadonly,
  normalizeAgentDraftPayload,
  type AgentDraftFormState,
  type AgentDraftTab,
} from "@/core/agents/agent-draft-lifecycle";
import {
  pathOfCreateAgentDraft,
  pathOfEditAgentDraft,
  resolveAgentDraftTab,
} from "@/core/agents/agent-draft-routes";
import {
  clearStoredAgentDraft,
  readStoredAgentDraft,
  writeStoredAgentDraft,
} from "@/core/agents/agent-draft-storage";
import { AgentNameCheckError, checkAgentName } from "@/core/agents/api";
import type { AgentDraftMode } from "@/core/agents/types";
import { useI18n } from "@/core/i18n/hooks";
import { useSkills } from "@/core/skills/hooks";
import { cn } from "@/lib/utils";

const NAME_RE = /^[A-Za-z0-9-]+$/;

interface AgentDraftFlowProps {
  mode: AgentDraftMode;
  agentName?: string | null;
}

export function AgentDraftFlow({ mode, agentName }: AgentDraftFlowProps) {
  const { t } = useI18n();
  const router = useRouter();
  const searchParams = useSearchParams();
  const { skills, isLoading: skillsLoading } = useSkills();
  const { agent, isLoading: agentLoading, error: agentError } = useAgent(
    mode === "edit" ? agentName : null,
  );
  const createAgentMutation = useCreateAgent();
  const updateAgentMutation = useUpdateAgent();

  const [form, setForm] = useState<AgentDraftFormState>(
    normalizeAgentDraftPayload(undefined),
  );
  const [initializedKey, setInitializedKey] = useState<string | null>(null);
  const [nameError, setNameError] = useState("");
  const [submitError, setSubmitError] = useState("");
  const [isCheckingName, setIsCheckingName] = useState(false);
  const [hasSavedDraft, setHasSavedDraft] = useState(false);

  const currentSearch = searchParams.toString();
  const activeTab = resolveAgentDraftTab(searchParams.get("tab"));
  const storageAgentName = mode === "edit" ? agentName ?? null : null;

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
      {
        id: "confirm" as const,
        label: t.agents.confirmSection,
        icon: CheckCircle2Icon,
      },
    ],
    [
      t.agents.confirmSection,
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

  useEffect(() => {
    const storageKey =
      mode === "create"
        ? "create"
        : agentName
          ? `edit:${agentName}`
          : null;

    if (!storageKey || initializedKey === storageKey || typeof window === "undefined") {
      return;
    }

    if (mode === "edit") {
      if (!agentName || agentLoading || !agent) {
        return;
      }
    }

    const storedDraft = readStoredAgentDraft(window.localStorage, mode, storageAgentName);
    const initialForm =
      storedDraft?.payload ??
      normalizeAgentDraftPayload({
        name: agent?.name ?? "",
        description: agent?.description ?? "",
        soul: agent?.soul ?? "",
        skills: agent?.skills ?? [],
      });

    setForm(initialForm);
    setHasSavedDraft(Boolean(storedDraft));
    setInitializedKey(storageKey);
  }, [
    agent,
    agentLoading,
    agentName,
    initializedKey,
    mode,
    storageAgentName,
  ]);

  useEffect(() => {
    if (!initializedKey || typeof window === "undefined") {
      return;
    }

    writeStoredAgentDraft(window.localStorage, {
      mode,
      agentName: storageAgentName,
      payload: form,
    });
    setHasSavedDraft(true);
  }, [form, initializedKey, mode, storageAgentName]);

  function navigateToTab(tab: AgentDraftTab) {
    const nextPath =
      mode === "create"
        ? pathOfCreateAgentDraft({ currentSearch, tab })
        : pathOfEditAgentDraft(agentName!, { currentSearch, tab });
    router.replace(nextPath);
  }

  function updateField<K extends keyof AgentDraftFormState>(
    field: K,
    value: AgentDraftFormState[K],
  ) {
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

  async function validateName() {
    if (mode === "edit") {
      return form.name;
    }

    const trimmed = form.name.trim();
    if (!trimmed) {
      setNameError(t.agents.createNameRequiredError);
      return null;
    }
    if (!NAME_RE.test(trimmed)) {
      setNameError(t.agents.nameStepInvalidError);
      return null;
    }

    setNameError("");
    setIsCheckingName(true);
    try {
      const result = await checkAgentName(trimmed);
      if (!result.available) {
        setNameError(t.agents.nameStepAlreadyExistsError);
        return null;
      }
      if (result.name !== form.name) {
        updateField("name", result.name);
      }
      return result.name;
    } catch (error) {
      if (error instanceof AgentNameCheckError) {
        if (error.reason === "backend_unreachable") {
          setNameError(t.agents.nameStepNetworkError);
        } else {
          setNameError(error.message || t.agents.nameStepCheckError);
        }
      } else {
        setNameError(t.agents.nameStepCheckError);
      }
      return null;
    } finally {
      setIsCheckingName(false);
    }
  }

  async function handleFinalize() {
    if (!canFinalizeAgentDraft(mode, form)) {
      navigateToTab("name");
      return;
    }

    setSubmitError("");
    let normalizedName = form.name.trim();
    if (mode === "create") {
      const checkedName = await validateName();
      if (!checkedName) {
        navigateToTab("name");
        return;
      }
      normalizedName = checkedName;
    }

    try {
      if (mode === "create") {
        await createAgentMutation.mutateAsync({
          name: normalizedName,
          description: form.description.trim(),
          soul: form.soul.trim(),
          skills: form.skills.length > 0 ? form.skills : null,
        });
      } else {
        await updateAgentMutation.mutateAsync({
          name: agentName!,
          request: {
            description: form.description.trim(),
            soul: form.soul.trim(),
            skills: form.skills,
          },
        });
      }

      if (typeof window !== "undefined") {
        clearStoredAgentDraft(window.localStorage, mode, storageAgentName);
      }

      toast.success(mode === "create" ? t.agents.createSuccess : t.agents.updateSuccess);
      router.push("/workspace/agents");
    } catch (error) {
      const message =
        error instanceof Error && error.message
          ? error.message
          : mode === "create"
            ? t.agents.createError
            : t.agents.updateError;
      setSubmitError(message);
      toast.error(message);
    }
  }

  const isSubmitting = createAgentMutation.isPending || updateAgentMutation.isPending;
  const isNameReadonly = isAgentDraftNameReadonly(mode);

  if (mode === "edit" && !agentName) {
    return <div className="p-6 text-sm text-muted-foreground">{t.agents.resumeDraftError}</div>;
  }

  if (mode === "edit" && agentLoading && initializedKey == null) {
    return <div className="p-6 text-sm text-muted-foreground">{t.common.loading}</div>;
  }

  if (mode === "edit" && agentError && initializedKey == null) {
    return <div className="p-6 text-sm text-destructive">{t.agents.resumeDraftError}</div>;
  }

  const shellTitle =
    mode === "create" ? t.agents.createPageTitle : t.agents.editPageTitle;
  const shellDescription =
    mode === "create" ? t.agents.createPageDescription : t.agents.editPageDescription;

  return (
    <div className="flex size-full flex-col">
      <div className="flex items-center justify-between border-b px-6 py-4">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-semibold">{shellTitle}</h1>
            {hasSavedDraft && (
              <span className="text-xs text-muted-foreground">{t.agents.draftSaved}</span>
            )}
          </div>
          <p className="text-sm text-muted-foreground">{shellDescription}</p>
        </div>
        <Button variant="ghost" onClick={() => router.push("/workspace/agents")}>
          <ArrowLeftIcon className="mr-2 h-4 w-4" />
          {t.agents.backToGallery}
        </Button>
      </div>

      <div className="min-h-0 flex-1 p-6">
        <Tabs
          orientation="vertical"
          value={activeTab}
          onValueChange={(value) => navigateToTab(resolveAgentDraftTab(value))}
          className="h-full gap-6 md:grid md:grid-cols-[240px_minmax(0,1fr)]"
        >
          <ScrollArea className="rounded-2xl border bg-card p-3">
            <TabsList variant="line" className="flex w-full flex-col items-stretch gap-2 bg-transparent p-0">
              {sections.map((section) => {
                const Icon = section.icon;
                return (
                  <TabsTrigger
                    key={section.id}
                    value={section.id}
                    className="justify-start rounded-xl border px-3 py-2.5"
                  >
                    <Icon className="h-4 w-4" />
                    <span>{section.label}</span>
                  </TabsTrigger>
                );
              })}
            </TabsList>
          </ScrollArea>

          <div className="min-w-0 rounded-2xl border bg-card p-6">
            <TabsContent value="name" className="space-y-4">
              <div className="space-y-2">
                <h2 className="text-2xl font-semibold">{t.agents.createNameTitle}</h2>
                <p className="text-sm text-muted-foreground">
                  {mode === "create" ? t.agents.createNameHint : t.agents.editNameHint}
                </p>
              </div>
              <Input
                autoFocus
                placeholder={t.agents.nameStepPlaceholder}
                value={form.name}
                readOnly={isNameReadonly}
                disabled={isNameReadonly}
                onChange={(event) => {
                  updateField("name", event.target.value);
                  setNameError("");
                  setSubmitError("");
                }}
                onBlur={() => void validateName()}
                className={cn(nameError && "border-destructive")}
              />
              {nameError && <p className="text-sm text-destructive">{nameError}</p>}
            </TabsContent>

            <TabsContent value="description" className="space-y-4">
              <div className="space-y-2">
                <h2 className="text-2xl font-semibold">{t.agents.createDescriptionTitle}</h2>
                <p className="text-sm text-muted-foreground">{t.agents.createDescriptionHint}</p>
              </div>
              <Textarea
                autoFocus
                value={form.description}
                onChange={(event) => updateField("description", event.target.value)}
                placeholder={t.agents.description}
                className="min-h-36"
              />
            </TabsContent>

            <TabsContent value="soul" className="space-y-4">
              <div className="space-y-2">
                <h2 className="text-2xl font-semibold">{t.agents.createSoulTitle}</h2>
                <p className="text-sm text-muted-foreground">{t.agents.createSoulHint}</p>
              </div>
              <Textarea
                autoFocus
                value={form.soul}
                onChange={(event) => updateField("soul", event.target.value)}
                placeholder="You are..."
                className="min-h-72"
              />
            </TabsContent>

            <TabsContent value="skills" className="space-y-4">
              <div className="space-y-2">
                <h2 className="text-2xl font-semibold">{t.agents.createSkillsTitle}</h2>
                <p className="text-sm text-muted-foreground">{t.agents.createSkillsHint}</p>
              </div>
              <div className="space-y-3">
                {skillsLoading ? (
                  <div className="text-sm text-muted-foreground">
                    {t.agents.createSkillsLoading}
                  </div>
                ) : visibleSkills.length === 0 ? (
                  <div className="text-sm text-muted-foreground">
                    {t.agents.createSkillsEmpty}
                  </div>
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
                        <Item variant="outline" className={cn(checked && "border-primary bg-primary/5")}>
                          <ItemContent>
                            <ItemTitle>{skill.name}</ItemTitle>
                            <ItemDescription>
                              {skill.description || t.agents.createSkillsHint}
                            </ItemDescription>
                          </ItemContent>
                          <ItemActions>
                            {checked && <CheckIcon className="h-4 w-4 text-primary" />}
                          </ItemActions>
                        </Item>
                      </button>
                    );
                  })
                )}
              </div>
            </TabsContent>

            <TabsContent value="confirm" className="space-y-6">
              <div className="space-y-2">
                <h2 className="text-2xl font-semibold">{t.agents.confirmTitle}</h2>
                <p className="text-sm text-muted-foreground">{t.agents.confirmHint}</p>
              </div>

              <div className="grid gap-4 md:grid-cols-2">
                <div className="rounded-2xl border p-4">
                  <div className="text-sm font-medium">{t.agents.createSectionName}</div>
                  <div className="mt-2 text-sm text-muted-foreground">
                    {form.name.trim() || t.agents.confirmEmptyValue}
                  </div>
                </div>
                <div className="rounded-2xl border p-4">
                  <div className="text-sm font-medium">{t.agents.createSectionDescription}</div>
                  <div className="mt-2 text-sm text-muted-foreground">
                    {form.description.trim() || t.agents.confirmEmptyValue}
                  </div>
                </div>
                <div className="rounded-2xl border p-4">
                  <div className="text-sm font-medium">{t.agents.createSectionSoul}</div>
                  <div className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap text-sm text-muted-foreground">
                    {form.soul.trim() || t.agents.confirmEmptyValue}
                  </div>
                </div>
                <div className="rounded-2xl border p-4">
                  <div className="text-sm font-medium">{t.agents.createSectionSkills}</div>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {form.skills.length === 0 ? (
                      <span className="text-sm text-muted-foreground">
                        {t.agents.confirmEmptyValue}
                      </span>
                    ) : (
                      form.skills.map((skillName) => (
                        <span
                          key={skillName}
                          className="rounded-full border px-2.5 py-1 text-xs text-muted-foreground"
                        >
                          {skillName}
                        </span>
                      ))
                    )}
                  </div>
                </div>
              </div>

              {submitError && <p className="text-sm text-destructive">{submitError}</p>}

              <div className="flex flex-wrap items-center justify-between gap-3">
                <p className="text-sm text-muted-foreground">{t.agents.confirmSubmitHint}</p>
                <Button
                  onClick={() => void handleFinalize()}
                  disabled={
                    isSubmitting ||
                    isCheckingName ||
                    (mode === "edit" && !!agentError) ||
                    !canFinalizeAgentDraft(mode, form)
                  }
                >
                  {isSubmitting
                    ? mode === "create"
                      ? t.agents.createButtonPending
                      : t.agents.updateButtonPending
                    : mode === "create"
                      ? t.agents.createButton
                      : t.agents.updateButton}
                </Button>
              </div>
            </TabsContent>
          </div>
        </Tabs>
      </div>
    </div>
  );
}

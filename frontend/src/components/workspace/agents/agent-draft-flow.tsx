"use client";

import {
  AlignLeftIcon,
  AlertTriangleIcon,
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
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Item,
  ItemActions,
  ItemContent,
  ItemDescription,
  ItemTitle,
} from "@/components/ui/item";
import { Progress } from "@/components/ui/progress";
import { Textarea } from "@/components/ui/textarea";
import { useAgent, useCreateAgent, useUpdateAgent } from "@/core/agents";
import {
  canFinalizeAgentDraft,
  isAgentDraftInputComplete,
  isAgentDraftNameReadonly,
  normalizeAgentDraftPayload,
  type AgentDraftFormState,
  type AgentDraftTab,
} from "@/core/agents/agent-draft-lifecycle";
import {
  pathOfCreateAgentDraft,
  resolveAgentDraftTab,
} from "@/core/agents/agent-draft-routes";
import {
  clearStoredAgentDraft,
  readStoredAgentDraft,
  writeStoredAgentDraft,
} from "@/core/agents/agent-draft-storage";
import { AgentNameCheckError, checkAgentName } from "@/core/agents/api";
import type { AgentDraftMode, AgentSkillMetadata } from "@/core/agents/types";
import { useI18n } from "@/core/i18n/hooks";
import {
  formatPlatformVersion,
  getAgentSkillBindingPlatformVersion,
  getSkillInstallState,
  getSkillPlatformVersion,
} from "@/core/skills/display";
import { useSkills } from "@/core/skills/hooks";
import type { Skill } from "@/core/skills/type";
import { cn } from "@/lib/utils";

const NAME_RE = /^[A-Za-z0-9-]+$/;

interface AgentDraftFlowProps {
  mode: AgentDraftMode;
  agentName?: string | null;
}

interface CreateStep {
  id: AgentDraftTab;
  label: string;
  icon: typeof BotIcon;
  preview: string;
  completed: boolean;
}

interface SkillDisplaySummary {
  name: string;
  description: string;
  versionLabel: string;
  sourceLabel: string;
  updateAvailable: boolean;
  unavailable: boolean;
}

export function AgentDraftFlow({ mode, agentName }: AgentDraftFlowProps) {
  const { t } = useI18n();
  const router = useRouter();
  const searchParams = useSearchParams();
  const { skills, isLoading: skillsLoading } = useSkills();
  const {
    agent,
    isLoading: agentLoading,
    error: agentError,
  } = useAgent(mode === "edit" ? agentName : null);
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
  const activeCreateTab =
    mode === "create" ? resolveAgentDraftTab(searchParams.get("tab")) : "name";
  const storageAgentName = mode === "edit" ? (agentName ?? null) : null;

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
  const visibleSkillByName = useMemo(
    () => new Map(visibleSkills.map((skill) => [skill.name, skill])),
    [visibleSkills],
  );
  const agentSkillMetadataByName = useMemo(
    () =>
      new Map(
        (agent?.skill_metadata ?? []).map((skill) => [skill.name, skill]),
      ),
    [agent?.skill_metadata],
  );

  function getSkillSourceLabel(skill: Skill): string {
    if (skill.category === "public") {
      return t.agents.skillSourceSkillHub;
    }
    return t.agents.skillSourceMySkills;
  }

  function getAgentSkillMetadataSourceLabel(skill: AgentSkillMetadata): string {
    if (skill.source === "skillhub") {
      return t.agents.skillSourceSkillHub;
    }
    if (skill.source === "my_skills") {
      return t.agents.skillSourceMySkills;
    }
    return skill.source_label || t.agents.skillSourceUnknown;
  }

  function getSkillSummary(skill: Skill): SkillDisplaySummary {
    const platformVersion = getSkillPlatformVersion(skill);
    const unavailable =
      skill.skill_install_id == null ||
      skill.skill_definition_id == null ||
      skill.skill_version_id == null ||
      platformVersion == null;
    return {
      name: skill.name,
      description: skill.description,
      versionLabel:
        formatPlatformVersion(platformVersion) ??
        t.agents.skillVersionUnavailable,
      sourceLabel: getSkillSourceLabel(skill),
      updateAvailable: getSkillInstallState(skill) === "update-available",
      unavailable,
    };
  }

  function getMetadataSummary(
    skill: AgentSkillMetadata,
  ): SkillDisplaySummary {
    return {
      name: skill.name,
      description: "",
      versionLabel:
        formatPlatformVersion(getAgentSkillBindingPlatformVersion(skill)) ??
        t.agents.skillVersionUnavailable,
      sourceLabel: getAgentSkillMetadataSourceLabel(skill),
      updateAvailable: skill.update_available === true,
      unavailable: skill.available === false || skill.status === "unavailable",
    };
  }

  const selectedSkillSummaries = form.skills.map((skillName) => {
    const visibleSkill = visibleSkillByName.get(skillName);
    if (visibleSkill) {
      return getSkillSummary(visibleSkill);
    }
    const metadata = agentSkillMetadataByName.get(skillName);
    if (metadata) {
      return getMetadataSummary(metadata);
    }
    return {
      name: skillName,
      description: "",
      versionLabel: t.agents.skillVersionUnavailable,
      sourceLabel: t.agents.skillSourceUnknown,
      updateAvailable: false,
      unavailable: true,
    };
  });

  const createSteps = useMemo<CreateStep[]>(
    () => [
      {
        id: "name",
        label: t.agents.createSectionName,
        icon: BotIcon,
        preview: form.name.trim() || t.agents.confirmEmptyValue,
        completed: isAgentDraftInputComplete("name", form),
      },
      {
        id: "description",
        label: t.agents.createSectionDescription,
        icon: AlignLeftIcon,
        preview: form.description.trim() || t.agents.confirmEmptyValue,
        completed: isAgentDraftInputComplete("description", form),
      },
      {
        id: "soul",
        label: t.agents.createSectionSoul,
        icon: FileTextIcon,
        preview: form.soul.trim() || t.agents.confirmEmptyValue,
        completed: isAgentDraftInputComplete("soul", form),
      },
      {
        id: "skills",
        label: t.agents.createSectionSkills,
        icon: SparklesIcon,
        preview:
          form.skills.length > 0
            ? form.skills.join(", ")
            : t.agents.confirmEmptyValue,
        completed: isAgentDraftInputComplete("skills", form),
      },
      {
        id: "confirm",
        label: t.agents.confirmSection,
        icon: CheckCircle2Icon,
        preview: t.agents.confirmSubmitHint,
        completed: false,
      },
    ],
    [
      form,
      t.agents.confirmEmptyValue,
      t.agents.confirmSection,
      t.agents.confirmSubmitHint,
      t.agents.createSectionDescription,
      t.agents.createSectionName,
      t.agents.createSectionSkills,
      t.agents.createSectionSoul,
    ],
  );

  const completedCreateStepCount = useMemo(
    () =>
      createSteps.filter((step) => step.id !== "confirm" && step.completed)
        .length,
    [createSteps],
  );

  const activeCreateStep =
    createSteps.find((step) => step.id === activeCreateTab) ?? createSteps[0]!;
  const activeCreateStepIndex = createSteps.findIndex(
    (step) => step.id === activeCreateStep.id,
  );
  const ActiveCreateStepIcon = activeCreateStep.icon;

  useEffect(() => {
    const storageKey =
      mode === "create" ? "create" : agentName ? `edit:${agentName}` : null;

    if (
      !storageKey ||
      initializedKey === storageKey ||
      typeof window === "undefined"
    ) {
      return;
    }

    if (mode === "edit") {
      if (!agentName || agentLoading || !agent) {
        return;
      }
    }

    const storedDraft = readStoredAgentDraft(
      window.localStorage,
      mode,
      storageAgentName,
    );
    const initialForm =
      storedDraft?.payload ??
      normalizeAgentDraftPayload({
        name: agent?.name ?? "",
        description: agent?.description ?? "",
        soul: agent?.soul ?? "",
        skills:
          agent?.skills ??
          agent?.skill_metadata?.map((skill) => skill.name) ??
          [],
      });

    setForm(initialForm);
    setHasSavedDraft(Boolean(storedDraft));
    setInitializedKey(storageKey);
  }, [agent, agentLoading, agentName, initializedKey, mode, storageAgentName]);

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

  function navigateToCreateTab(tab: AgentDraftTab) {
    if (mode !== "create") {
      return;
    }

    router.replace(pathOfCreateAgentDraft({ currentSearch, tab }));
  }

  function updateField<K extends keyof AgentDraftFormState>(
    field: K,
    value: AgentDraftFormState[K],
  ) {
    setForm((current) => ({ ...current, [field]: value }));
    setSubmitError("");
    if (field === "name") {
      setNameError("");
    }
  }

  function toggleSkill(skillName: string, options?: { canAdd?: boolean }) {
    setSubmitError("");
    setForm((current) => {
      if (current.skills.includes(skillName)) {
        return {
          ...current,
          skills: current.skills.filter((name) => name !== skillName),
        };
      }
      if (options?.canAdd === false) {
        return current;
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
      if (mode === "create") {
        navigateToCreateTab("name");
      }
      return;
    }

    setSubmitError("");
    let normalizedName = form.name.trim();
    if (mode === "create") {
      const checkedName = await validateName();
      if (!checkedName) {
        navigateToCreateTab("name");
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

      toast.success(
        mode === "create" ? t.agents.createSuccess : t.agents.updateSuccess,
      );
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

  const isSubmitting =
    createAgentMutation.isPending || updateAgentMutation.isPending;
  const isNameReadonly = isAgentDraftNameReadonly(mode);

  function renderNameSection(options?: { autoFocus?: boolean }) {
    return (
      <div className="space-y-4">
        <div className="space-y-2">
          <h2 className="text-2xl font-semibold">{t.agents.createNameTitle}</h2>
          <p className="text-muted-foreground text-sm">
            {mode === "create"
              ? t.agents.createNameHint
              : t.agents.editNameHint}
          </p>
        </div>
        <Input
          autoFocus={options?.autoFocus}
          placeholder={t.agents.nameStepPlaceholder}
          value={form.name}
          readOnly={isNameReadonly}
          disabled={isNameReadonly}
          onChange={(event) => updateField("name", event.target.value)}
          onBlur={() => {
            if (mode === "create") {
              void validateName();
            }
          }}
          className={cn(nameError && "border-destructive")}
        />
        {nameError && <p className="text-destructive text-sm">{nameError}</p>}
      </div>
    );
  }

  function renderDescriptionSection(options?: { autoFocus?: boolean }) {
    return (
      <div className="space-y-4">
        <div className="space-y-2">
          <h2 className="text-2xl font-semibold">
            {t.agents.createDescriptionTitle}
          </h2>
          <p className="text-muted-foreground text-sm">
            {t.agents.createDescriptionHint}
          </p>
        </div>
        <Textarea
          autoFocus={options?.autoFocus}
          value={form.description}
          onChange={(event) => updateField("description", event.target.value)}
          placeholder={t.agents.description}
          className="min-h-36"
        />
      </div>
    );
  }

  function renderSoulSection(options?: { autoFocus?: boolean }) {
    return (
      <div className="space-y-4">
        <div className="space-y-2">
          <h2 className="text-2xl font-semibold">{t.agents.createSoulTitle}</h2>
          <p className="text-muted-foreground text-sm">
            {t.agents.createSoulHint}
          </p>
        </div>
        <Textarea
          autoFocus={options?.autoFocus}
          value={form.soul}
          onChange={(event) => updateField("soul", event.target.value)}
          placeholder="You are..."
          className="min-h-72"
        />
      </div>
    );
  }

  function renderSkillsSection() {
    return (
      <div className="space-y-4">
        <div className="space-y-2">
          <h2 className="text-2xl font-semibold">
            {t.agents.createSkillsTitle}
          </h2>
          <p className="text-muted-foreground text-sm">
            {t.agents.createSkillsHint}
          </p>
        </div>
        <div className="space-y-3">
          {skillsLoading ? (
            <div className="text-muted-foreground text-sm">
              {t.agents.createSkillsLoading}
            </div>
          ) : visibleSkills.length === 0 ? (
            <div className="text-muted-foreground text-sm">
              {t.agents.createSkillsEmpty}
            </div>
          ) : (
            visibleSkills.map((skill) => {
              const checked = form.skills.includes(skill.name);
              const summary = getSkillSummary(skill);
              const cannotAdd = summary.unavailable && !checked;
              return (
                <button
                  key={skill.name}
                  type="button"
                  aria-pressed={checked}
                  disabled={cannotAdd}
                  onClick={() =>
                    toggleSkill(skill.name, { canAdd: !summary.unavailable })
                  }
                  className="block w-full text-left"
                >
                  <Item
                    variant="outline"
                    className={cn(
                      checked && "border-primary bg-primary/5",
                      cannotAdd && "opacity-60",
                    )}
                  >
                    <ItemContent>
                      <ItemTitle className="flex flex-wrap items-center gap-2">
                        <span>{skill.name}</span>
                        {summary.unavailable && (
                          <span className="text-destructive inline-flex items-center gap-1 text-xs font-normal">
                            <AlertTriangleIcon className="h-3.5 w-3.5" />
                            {t.agents.skillMetadataUnavailable}
                          </span>
                        )}
                      </ItemTitle>
                      <ItemDescription>
                        {skill.description || t.agents.createSkillsHint}
                      </ItemDescription>
                      <div className="text-muted-foreground mt-2 flex flex-wrap gap-2 text-xs">
                        <span>{summary.versionLabel}</span>
                        <span>{summary.sourceLabel}</span>
                        {summary.updateAvailable && (
                          <span className="text-primary">
                            {t.agents.skillUpdateAvailable}
                          </span>
                        )}
                      </div>
                    </ItemContent>
                    <ItemActions>
                      {checked && (
                        <CheckIcon className="text-primary h-4 w-4" />
                      )}
                    </ItemActions>
                  </Item>
                </button>
              );
            })
          )}
        </div>
      </div>
    );
  }

  function renderConfirmSection() {
    return (
      <div className="space-y-6">
        <div className="space-y-2">
          <h2 className="text-2xl font-semibold">{t.agents.confirmTitle}</h2>
          <p className="text-muted-foreground text-sm">
            {t.agents.confirmHint}
          </p>
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <div className="rounded-2xl border p-4">
            <div className="text-sm font-medium">
              {t.agents.createSectionName}
            </div>
            <div className="text-muted-foreground mt-2 text-sm">
              {form.name.trim() || t.agents.confirmEmptyValue}
            </div>
          </div>
          <div className="rounded-2xl border p-4">
            <div className="text-sm font-medium">
              {t.agents.createSectionDescription}
            </div>
            <div className="text-muted-foreground mt-2 text-sm">
              {form.description.trim() || t.agents.confirmEmptyValue}
            </div>
          </div>
          <div className="rounded-2xl border p-4">
            <div className="text-sm font-medium">
              {t.agents.createSectionSoul}
            </div>
            <div className="text-muted-foreground mt-2 max-h-40 overflow-auto text-sm whitespace-pre-wrap">
              {form.soul.trim() || t.agents.confirmEmptyValue}
            </div>
          </div>
          <div className="rounded-2xl border p-4">
            <div className="text-sm font-medium">
              {t.agents.createSectionSkills}
            </div>
            <div className="mt-2 flex flex-wrap gap-2">
              {form.skills.length === 0 ? (
                <span className="text-muted-foreground text-sm">
                  {t.agents.confirmEmptyValue}
                </span>
              ) : (
                selectedSkillSummaries.map((skill) => (
                  <span
                    key={skill.name}
                    className={cn(
                      "text-muted-foreground rounded-md border px-2.5 py-1 text-xs",
                      skill.unavailable && "border-destructive/40 text-destructive",
                    )}
                  >
                    {skill.name} · {skill.versionLabel} · {skill.sourceLabel}
                    {skill.updateAvailable
                      ? ` · ${t.agents.skillUpdateAvailable}`
                      : ""}
                    {skill.unavailable
                      ? ` · ${t.agents.skillMetadataUnavailable}`
                      : ""}
                  </span>
                ))
              )}
            </div>
          </div>
        </div>

        {submitError && (
          <p className="text-destructive text-sm">{submitError}</p>
        )}
      </div>
    );
  }

  function renderCreateStepContent() {
    switch (activeCreateTab) {
      case "description":
        return renderDescriptionSection({ autoFocus: true });
      case "soul":
        return renderSoulSection({ autoFocus: true });
      case "skills":
        return renderSkillsSection();
      case "confirm":
        return renderConfirmSection();
      case "name":
      default:
        return renderNameSection({ autoFocus: true });
    }
  }

  function renderCreateStepActions() {
    const previousStep =
      activeCreateStepIndex > 0 ? createSteps[activeCreateStepIndex - 1] : null;
    const nextStep =
      activeCreateStepIndex < createSteps.length - 1
        ? createSteps[activeCreateStepIndex + 1]
        : null;

    return (
      <div className="flex flex-wrap items-center justify-between gap-3 border-t pt-6">
        {previousStep ? (
          <Button
            variant="outline"
            onClick={() => navigateToCreateTab(previousStep.id)}
          >
            {t.common.previous}
          </Button>
        ) : (
          <span />
        )}

        {nextStep ? (
          <Button onClick={() => navigateToCreateTab(nextStep.id)}>
            {t.common.next}
          </Button>
        ) : (
          <Button
            onClick={() => void handleFinalize()}
            disabled={
              isSubmitting ||
              isCheckingName ||
              !canFinalizeAgentDraft(mode, form)
            }
          >
            {isSubmitting
              ? t.agents.createButtonPending
              : t.agents.createButton}
          </Button>
        )}
      </div>
    );
  }

  if (mode === "edit" && !agentName) {
    return (
      <div className="text-muted-foreground p-6 text-sm">
        {t.agents.resumeDraftError}
      </div>
    );
  }

  if (mode === "edit" && agentLoading && initializedKey == null) {
    return (
      <div className="text-muted-foreground p-6 text-sm">
        {t.common.loading}
      </div>
    );
  }

  if (mode === "edit" && agentError && initializedKey == null) {
    return (
      <div className="text-destructive p-6 text-sm">
        {t.agents.resumeDraftError}
      </div>
    );
  }

  const shellTitle =
    mode === "create" ? t.agents.createPageTitle : t.agents.editPageTitle;
  const shellDescription =
    mode === "create"
      ? t.agents.createPageDescription
      : t.agents.editPageDescription;

  return (
    <div className="flex size-full flex-col">
      <div className="flex items-center justify-between border-b px-6 py-4">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-semibold">{shellTitle}</h1>
            {hasSavedDraft && (
              <span className="text-muted-foreground text-xs">
                {t.agents.draftSaved}
              </span>
            )}
          </div>
          <p className="text-muted-foreground text-sm">{shellDescription}</p>
        </div>
        <Button
          variant="ghost"
          onClick={() => router.push("/workspace/agents")}
        >
          <ArrowLeftIcon className="mr-2 h-4 w-4" />
          {t.agents.backToGallery}
        </Button>
      </div>

      <div className="min-h-0 flex-1 p-6">
        {mode === "create" ? (
          <div className="mx-auto grid h-full max-w-6xl gap-6 lg:grid-cols-[280px_minmax(0,1fr)]">
            <Card className="h-fit gap-4 py-4">
              <CardHeader className="px-4">
                <div className="flex items-center justify-between gap-3">
                  <div className="space-y-1">
                    <CardTitle className="text-base">
                      {t.agents.createPageTitle}
                    </CardTitle>
                    <CardDescription>
                      {t.agents.createPageDescription}
                    </CardDescription>
                  </div>
                  <span className="text-muted-foreground text-sm font-medium">
                    {completedCreateStepCount}/4
                  </span>
                </div>
                <Progress value={(completedCreateStepCount / 4) * 100} />
              </CardHeader>

              <CardContent className="space-y-2 px-4">
                {createSteps.map((step, index) => {
                  const StepIcon = step.icon;
                  const isActive = step.id === activeCreateStep.id;

                  return (
                    <button
                      key={step.id}
                      type="button"
                      onClick={() => navigateToCreateTab(step.id)}
                      className={cn(
                        "w-full rounded-xl border px-3 py-3 text-left transition-colors",
                        isActive
                          ? "border-primary bg-primary/5"
                          : "hover:border-primary/40 hover:bg-accent/30",
                      )}
                    >
                      <div className="flex items-start gap-3">
                        <div
                          className={cn(
                            "mt-0.5 flex size-8 items-center justify-center rounded-full border text-xs font-semibold",
                            step.completed
                              ? "border-primary bg-primary text-primary-foreground"
                              : isActive
                                ? "border-primary text-primary"
                                : "text-muted-foreground",
                          )}
                        >
                          {step.completed ? (
                            <CheckIcon className="h-4 w-4" />
                          ) : (
                            index + 1
                          )}
                        </div>

                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-medium">
                              {step.label}
                            </span>
                            <StepIcon className="text-muted-foreground h-4 w-4" />
                          </div>
                          <p className="text-muted-foreground mt-1 truncate text-xs">
                            {step.preview}
                          </p>
                        </div>
                      </div>
                    </button>
                  );
                })}
              </CardContent>
            </Card>

            <Card className="min-h-[560px] py-0">
              <CardHeader className="border-b py-6">
                <div className="text-muted-foreground flex items-center gap-2 text-sm">
                  <ActiveCreateStepIcon className="h-4 w-4" />
                  <span>{activeCreateStep.label}</span>
                </div>
              </CardHeader>

              <CardContent className="flex flex-1 flex-col gap-6 py-6">
                <div className="flex-1">{renderCreateStepContent()}</div>
                {renderCreateStepActions()}
              </CardContent>
            </Card>
          </div>
        ) : (
          <div className="mx-auto max-w-5xl">
            <Card className="py-0">
              <CardHeader className="border-b py-6">
                <CardTitle>{t.agents.editPageTitle}</CardTitle>
                <CardDescription>
                  {t.agents.editPageDescription}
                </CardDescription>
              </CardHeader>

              <CardContent className="space-y-6 py-6">
                {renderNameSection()}

                <div className="border-t pt-6">
                  {renderDescriptionSection()}
                </div>

                <div className="border-t pt-6">{renderSoulSection()}</div>

                <div className="border-t pt-6">{renderSkillsSection()}</div>

                {submitError && (
                  <p className="text-destructive text-sm">{submitError}</p>
                )}
              </CardContent>

              <CardFooter className="justify-end border-t py-6">
                <Button
                  onClick={() => void handleFinalize()}
                  disabled={isSubmitting || !!agentError}
                >
                  {isSubmitting
                    ? t.agents.updateButtonPending
                    : t.agents.updateButton}
                </Button>
              </CardFooter>
            </Card>
          </div>
        )}
      </div>
    </div>
  );
}

"use client";

import {
  DownloadIcon,
  MoreVerticalIcon,
  PackageIcon,
  SearchIcon,
  UploadIcon,
} from "lucide-react";
import { type ChangeEvent, useRef, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty";
import {
  InputGroup,
  InputGroupAddon,
  InputGroupInput,
} from "@/components/ui/input-group";
import {
  Item,
  ItemActions,
  ItemContent,
  ItemDescription,
  ItemTitle,
} from "@/components/ui/item";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useI18n } from "@/core/i18n/hooks";
import {
  checkSkillHubInstall,
  checkSkillUpload,
  getSkillInstallUpdateDialogState,
  useConfirmSkillInstallUpdate,
  useDeleteSkill,
  useDownloadSkillForkPackage,
  useInstallSkillHubSkill,
  usePublishSkill,
  usePreviewSkillInstallUpdate,
  useSkills,
  useUploadSkills,
} from "@/core/skills";
import {
  findInstalledSkillForSkillHubItem,
  canCreateMyVersionFromSkillHubItem,
  getSkillDisplayContract,
  getSkillHubLatestPlatformVersion,
  getSkillInstallState,
  getSkillPlatformVersion,
  getSkillWorkspaceCardState,
  isCommunitySkill,
  isPersonalSkill,
  isSystemSkill,
  skillMatchesCommunitySearch,
  skillMatchesWorkspaceSegment,
  type SkillInstallState,
  type SkillWorkspacePrimaryAction,
  type SkillWorkspaceSegment,
} from "@/core/skills/display";
import type { Skill } from "@/core/skills/type";

type SkillsSurface = "system" | "community" | "personal";

type SkillGalleryEmptyContent = {
  title: string;
  description: string;
  icon: "search" | "package";
  action: "clear-search" | "browse-community" | "upload" | null;
};

const SKILL_SURFACE_SEGMENTS: Record<SkillsSurface, SkillWorkspaceSegment[]> = {
  system: ["all"],
  community: ["all"],
  personal: ["all", "authored", "installed", "updates"],
};

export function SkillsGallery() {
  const { t } = useI18n();
  const { skills, isLoading, error } = useSkills();
  const deleteSkill = useDeleteSkill();
  const installSkillHubSkill = useInstallSkillHubSkill();
  const downloadForkPackage = useDownloadSkillForkPackage();
  const confirmSkillUpdate = useConfirmSkillInstallUpdate();
  const publishSkill = usePublishSkill();
  const uploadSkills = useUploadSkills();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [surface, setSurface] = useState<SkillsSurface>("system");
  const [segment, setSegment] = useState<SkillWorkspaceSegment>("all");
  const [communitySearch, setCommunitySearch] = useState("");
  const [publishCandidate, setPublishCandidate] = useState<Skill | null>(null);
  const [updateCandidate, setUpdateCandidate] = useState<Skill | null>(null);
  const [installingSkillKey, setInstallingSkillKey] = useState<string | null>(
    null,
  );
  const [downloadingSkillKey, setDownloadingSkillKey] = useState<string | null>(
    null,
  );
  const [releaseNotes, setReleaseNotes] = useState("");
  const updatePreview = usePreviewSkillInstallUpdate(
    updateCandidate?.name ?? null,
    updateCandidate?.skill_install_id ?? null,
  );
  const updateDialogState = getSkillInstallUpdateDialogState(
    updatePreview.data ?? null,
    {
      isPreviewLoading: updatePreview.isLoading,
      isConfirming: confirmSkillUpdate.isPending,
    },
  );

  const filteredSkills = skills.filter((skill) => {
    const installedSkill = findInstalledSkillForSkillHubItem(skill, skills);
    const inSurface = (() => {
      switch (surface) {
        case "system":
          return isSystemSkill(skill);
        case "community":
          return isCommunitySkill(skill);
        case "personal":
          return isPersonalSkill(skill);
      }
    })();
    const matchesSearch =
      surface !== "community" ||
      skillMatchesCommunitySearch(skill, communitySearch);
    return (
      inSurface &&
      matchesSearch &&
      skillMatchesWorkspaceSegment(skill, segment, installedSkill)
    );
  });

  function getVersionText(version: number | null) {
    if (version != null) {
      return t.settings.skills.platformVersion(version);
    }
    return t.settings.skills.noPlatformVersion;
  }

  function getSkillHubVersionDetail(skill: Skill) {
    const latestVersion = getSkillHubLatestPlatformVersion(skill);

    if (latestVersion != null) {
      return t.settings.skills.skillHubVersion(latestVersion);
    }

    return t.settings.skills.noPlatformVersion;
  }

  function getMySkillVersionDetail(skill: Skill) {
    const version = getSkillPlatformVersion(skill);
    return version != null
      ? t.settings.skills.currentVersion(version)
      : t.settings.skills.noPlatformVersion;
  }

  function getSkillSourceText(skill: Skill) {
    const display = getSkillDisplayContract(skill);
    if (display.sourceKind === "official") {
      return t.settings.skills.officialSource;
    }
    if (
      display.space === "community" &&
      (display.viewerRelation === "authored_published" ||
        display.viewerRelation === "authored_unpublished_changes")
    ) {
      return t.settings.skills.publishedByYou;
    }
    if (display.space === "community") {
      return skill.owner_display_name
        ? t.settings.skills.communitySource(skill.owner_display_name)
        : t.settings.skills.communitySource(
            t.settings.skills.communitySpaceSource,
          );
    }
    if (
      display.viewerRelation === "downloaded" ||
      display.viewerRelation === "update_available"
    ) {
      return t.settings.skills.installedFromSource(
        skill.owner_display_name ?? t.settings.skills.communitySpaceSource,
      );
    }
    if (display.viewerRelation === "forked") {
      if (skill.fork_source_skill_name) {
        return t.settings.skills.forkedSourceDetail(
          skill.fork_source_skill_name,
          skill.fork_source_owner_display_name ??
            t.settings.skills.communitySpaceSource,
          skill.fork_source_platform_version ?? null,
        );
      }
      return skill.owner_display_name
        ? t.settings.skills.forkedSource(skill.owner_display_name)
        : t.settings.skills.createdSource;
    }
    return t.settings.skills.createdSource;
  }

  function getSegmentText(value: SkillWorkspaceSegment) {
    switch (value) {
      case "installed":
        return t.settings.skills.installedSegment;
      case "authored":
        return t.settings.skills.authoredSegment;
      case "updates":
        return t.settings.skills.updatesSegment;
      case "all":
        return t.settings.skills.allSegment;
    }
  }

  function getWorkspaceStatusText(
    skill: Skill,
    action: SkillWorkspacePrimaryAction,
    installState: SkillInstallState,
  ) {
    const display = getSkillDisplayContract(skill);
    if (
      display.viewerRelation === "authored_unpublished_changes" ||
      action === "publish-update"
    ) {
      return t.settings.skills.unpublishedChanges;
    }
    if (display.viewerRelation === "authored_published") {
      return t.settings.skills.published;
    }
    if (display.space === "personal" && display.viewerRelation === "authored") {
      return t.settings.skills.mySkill;
    }
    if (display.viewerRelation === "forked") {
      return t.settings.skills.mySkill;
    }
    if (action === "view-update" || installState === "update-available") {
      return t.settings.skills.updateAvailable;
    }
    if (action === "view-personal" || display.viewerRelation === "downloaded") {
      return t.settings.skills.installedToPersonal;
    }
    return t.settings.skills.availableInCommunity;
  }

  function getPrimaryActionText(action: SkillWorkspacePrimaryAction) {
    switch (action) {
      case "add-to-personal":
        return t.settings.skills.addToPersonalSpace;
      case "view-personal":
        return t.settings.skills.viewInPersonalSpace;
      case "view-update":
        return t.settings.skills.viewUpdate;
      case "publish":
        return t.settings.skills.publishSkill;
      case "publish-update":
        return t.settings.skills.publishUpdate;
      case "none":
        return null;
    }
  }

  function getAffectedAgentsText(agentNames: string[]) {
    if (agentNames.length === 0) {
      return t.settings.skills.noAffectedAgents;
    }
    return agentNames.join(", ");
  }

  function getEmptyStateContent(): SkillGalleryEmptyContent {
    if (surface === "system") {
      return {
        title: t.settings.skills.noSystemSkills,
        description: t.settings.skills.noSystemSkillsDescription,
        icon: "package" as const,
        action: null,
      };
    }

    if (surface === "community") {
      if (communitySearch.trim()) {
        return {
          title: t.settings.skills.noCommunitySearchResults,
          description: t.settings.skills.noCommunitySearchResultsDescription,
          icon: "search" as const,
          action: "clear-search" as const,
        };
      }

      return {
        title: t.settings.skills.noSkillHubSkills,
        description: t.settings.skills.noSkillHubSkillsDescription,
        icon: "package" as const,
        action: null,
      };
    }

    switch (segment) {
      case "authored":
        return {
          title: t.settings.skills.noAuthoredSkills,
          description: t.settings.skills.noAuthoredSkillsDescription,
          icon: "package" as const,
          action: "upload" as const,
        };
      case "installed":
        return {
          title: t.settings.skills.noInstalledSkills,
          description: t.settings.skills.noInstalledSkillsDescription,
          icon: "package" as const,
          action: "browse-community" as const,
        };
      case "updates":
        return {
          title: t.settings.skills.noSkillUpdates,
          description: t.settings.skills.noSkillUpdatesDescription,
          icon: "package" as const,
          action: null,
        };
      case "all":
        return {
          title: t.settings.skills.noMySkills,
          description: t.settings.skills.noMySkillsDescription,
          icon: "package" as const,
          action: "upload" as const,
        };
    }
  }

  function openUploadDialog() {
    fileInputRef.current?.click();
  }

  async function handleDelete(skill: Skill) {
    const confirmed = window.confirm(`${t.common.delete} ${skill.name}?`);
    if (!confirmed) {
      return;
    }

    try {
      await deleteSkill.mutateAsync(skill.name);
      toast.success(`${skill.name} ${t.common.delete}`);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      const match = /agent '([^']+)'/.exec(message);
      if (match?.[1]) {
        toast.error(t.settings.skills.deleteBlocked(match[1]));
        return;
      }
      toast.error(message);
    }
  }

  async function handleInstall(skill: Skill, skillKey: string) {
    if (installingSkillKey !== null) {
      return;
    }

    setInstallingSkillKey(skillKey);
    try {
      const result = await checkSkillHubInstall(skill.name, {
        owner_user_id: skill.owner_user_id ?? null,
        skill_definition_id: skill.skill_definition_id ?? null,
      });
      const overwrite = result.exists
        ? window.confirm(t.settings.skills.conflictConfirm(result.skill_name))
        : false;

      if (result.exists && !overwrite) {
        return;
      }

      await installSkillHubSkill.mutateAsync({
        skillName: skill.name,
        ownerUserId: skill.owner_user_id ?? null,
        skillDefinitionId: skill.skill_definition_id ?? null,
        overwrite,
      });
      toast.success(t.settings.skills.installSuccess(skill.name));
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : t.settings.skills.installError,
      );
    } finally {
      setInstallingSkillKey(null);
    }
  }

  async function handleUpdateConfirmed() {
    if (!updateCandidate || !updatePreview.data?.target_skill_version_id) {
      return;
    }

    try {
      await confirmSkillUpdate.mutateAsync({
        skillName: updateCandidate.name,
        skillInstallId: updateCandidate.skill_install_id ?? null,
        skillVersionId: updatePreview.data.target_skill_version_id,
      });
      toast.success(t.settings.skills.updateSuccess(updateCandidate.name));
      setUpdateCandidate(null);
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : t.settings.skills.updateError,
      );
    }
  }

  async function handleDownloadForkPackage(skill: Skill, skillKey: string) {
    if (downloadingSkillKey !== null) {
      return;
    }

    setDownloadingSkillKey(skillKey);
    try {
      await downloadForkPackage.mutateAsync({
        skillName: skill.name,
        ownerUserId: skill.owner_user_id ?? null,
        skillDefinitionId: skill.skill_definition_id ?? null,
      });
      toast.success(t.settings.skills.forkDownloadSuccess);
    } catch (error) {
      toast.error(
        error instanceof Error
          ? error.message
          : t.settings.skills.forkDownloadError,
      );
    } finally {
      setDownloadingSkillKey(null);
    }
  }

  async function handlePublishConfirmed() {
    if (!publishCandidate) {
      return;
    }

    try {
      await publishSkill.mutateAsync({
        skillName: publishCandidate.name,
        releaseNotes: releaseNotes.trim() || null,
      });
      toast.success(t.settings.skills.publishSuccess(publishCandidate.name));
      setPublishCandidate(null);
      setReleaseNotes("");
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : t.settings.skills.uploadError,
      );
    }
  }

  async function handleFilesSelected(event: ChangeEvent<HTMLInputElement>) {
    const fileList = event.target.files;
    if (!fileList || fileList.length === 0) {
      return;
    }

    const files = Array.from(fileList);
    const filesToUpload: File[] = [];
    const overwriteNames: string[] = [];

    for (const file of files) {
      try {
        const result = await checkSkillUpload(file);
        if (result.exists) {
          const shouldOverwrite = window.confirm(
            t.settings.skills.conflictConfirm(result.skill_name),
          );
          if (!shouldOverwrite) {
            continue;
          }
          overwriteNames.push(result.skill_name);
        }
        filesToUpload.push(file);
      } catch (error) {
        toast.error(
          error instanceof Error
            ? error.message
            : t.settings.skills.uploadError,
        );
      }
    }

    if (filesToUpload.length === 0) {
      event.target.value = "";
      return;
    }

    try {
      const response = await uploadSkills.mutateAsync({
        files: filesToUpload,
        overwriteNames,
      });
      const failed = response.results.filter((result) => !result.success);
      const succeeded = response.results.filter((result) => result.success);

      if (succeeded.length > 0) {
        toast.success(t.settings.skills.uploadSuccess);
      }
      for (const result of failed) {
        toast.error(`${result.filename}: ${result.message}`);
      }
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : t.settings.skills.uploadError,
      );
    } finally {
      event.target.value = "";
    }
  }

  return (
    <div className="flex size-full flex-col">
      <div className="flex items-center justify-between border-b px-6 py-4">
        <div>
          <h1 className="text-xl font-semibold">{t.settings.skills.title}</h1>
          <p className="text-muted-foreground mt-0.5 text-sm">
            {t.settings.skills.description}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <input
            ref={fileInputRef}
            type="file"
            accept=".zip"
            multiple
            className="hidden"
            onChange={(event) => void handleFilesSelected(event)}
          />
          <Button onClick={openUploadDialog} disabled={uploadSkills.isPending}>
            <UploadIcon className="mr-1.5 h-4 w-4" />
            {uploadSkills.isPending
              ? t.settings.skills.uploadPending
              : t.settings.skills.uploadSkill}
          </Button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-6">
        <div className="mb-4 flex gap-2">
          <Tabs
            value={surface}
            onValueChange={(value) => {
              setSurface(value as SkillsSurface);
              setSegment("all");
            }}
          >
            <TabsList variant="line">
              <TabsTrigger value="system">
                {t.settings.skills.systemSpaceTab}
              </TabsTrigger>
              <TabsTrigger value="community">
                {t.settings.skills.communitySpaceTab}
              </TabsTrigger>
              <TabsTrigger value="personal">
                {t.settings.skills.personalSpaceTab}
              </TabsTrigger>
            </TabsList>
          </Tabs>
        </div>
        {SKILL_SURFACE_SEGMENTS[surface].length > 1 ? (
          <div className="mb-5 flex gap-2">
            <Tabs
              value={segment}
              onValueChange={(value) =>
                setSegment(value as SkillWorkspaceSegment)
              }
            >
              <TabsList variant="line">
                {SKILL_SURFACE_SEGMENTS[surface].map((value) => (
                  <TabsTrigger key={value} value={value}>
                    {getSegmentText(value)}
                  </TabsTrigger>
                ))}
              </TabsList>
            </Tabs>
          </div>
        ) : null}
        {surface === "community" ? (
          <div className="mb-5 max-w-xl">
            <InputGroup>
              <InputGroupAddon>
                <SearchIcon className="size-4" />
              </InputGroupAddon>
              <InputGroupInput
                type="search"
                value={communitySearch}
                placeholder={t.settings.skills.communitySearchPlaceholder}
                aria-label={t.settings.skills.communitySearchPlaceholder}
                onChange={(event) => setCommunitySearch(event.target.value)}
              />
            </InputGroup>
          </div>
        ) : null}

        {isLoading ? (
          <div className="text-muted-foreground text-sm">
            {t.common.loading}
          </div>
        ) : error ? (
          <div className="text-destructive text-sm">{error.message}</div>
        ) : filteredSkills.length === 0 ? (
          <SkillGalleryEmptyState
            content={getEmptyStateContent()}
            isUploadPending={uploadSkills.isPending}
            onBrowseCommunity={() => {
              setSurface("community");
              setSegment("all");
              setCommunitySearch("");
            }}
            onClearSearch={() => setCommunitySearch("")}
            onUpload={openUploadDialog}
          />
        ) : (
          <div className="space-y-4">
            {filteredSkills.map((skill) => {
              const display = getSkillDisplayContract(skill);
              const installedSkill = findInstalledSkillForSkillHubItem(
                skill,
                skills,
              );
              const installState = getSkillInstallState(skill, installedSkill);
              const cardState = getSkillWorkspaceCardState(
                skill,
                installedSkill,
              );
              const communityActionInstalled = installState !== "not-installed";
              const shouldShowCommunityInstallAction =
                cardState.primaryAction === "add-to-personal" ||
                communityActionInstalled;
              const canCreateMyVersion =
                canCreateMyVersionFromSkillHubItem(skill);
              const platformVersion =
                display.space === "community" || display.space === "system"
                  ? getSkillHubLatestPlatformVersion(skill)
                  : getSkillPlatformVersion(skill);
              const isInstallingSkill =
                installingSkillKey === display.identityKey;
              const isDownloadingSkill =
                downloadingSkillKey === display.identityKey;
              const primaryActionText = getPrimaryActionText(
                cardState.primaryAction,
              );

              return (
                <Item
                  key={display.identityKey}
                  className="w-full"
                  variant="outline"
                >
                  <ItemContent>
                    <div className="flex flex-wrap items-center gap-2">
                      <ItemTitle>{skill.name}</ItemTitle>
                      <Badge
                        variant={
                          platformVersion != null ? "secondary" : "outline"
                        }
                      >
                        {getVersionText(platformVersion)}
                      </Badge>
                      {display.space === "personal" ? (
                        <Badge
                          variant={
                            installState === "update-available"
                              ? "default"
                              : "outline"
                          }
                        >
                          {getWorkspaceStatusText(
                            skill,
                            cardState.primaryAction,
                            installState,
                          )}
                        </Badge>
                      ) : null}
                      {display.space === "system" ? (
                        <Badge variant="outline">
                          {t.settings.skills.systemDirectUse}
                        </Badge>
                      ) : null}
                    </div>
                    <div className="text-muted-foreground mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
                      <span>
                        {display.space === "system"
                          ? getMySkillVersionDetail(skill)
                          : display.space === "community"
                            ? getSkillHubVersionDetail(skill)
                            : getMySkillVersionDetail(skill)}
                      </span>
                      <span>{getSkillSourceText(skill)}</span>
                    </div>
                    <ItemDescription className="line-clamp-4">
                      {skill.description}
                    </ItemDescription>
                  </ItemContent>
                  <ItemActions>
                    {display.space === "system" ? null : display.space ===
                      "community" ? (
                      <div className="flex items-center gap-2">
                        {shouldShowCommunityInstallAction ? (
                          <Button
                            size="sm"
                            variant={
                              communityActionInstalled ? "outline" : "default"
                            }
                            disabled={
                              communityActionInstalled ||
                              installingSkillKey !== null
                            }
                            onClick={() => {
                              if (!communityActionInstalled) {
                                void handleInstall(skill, display.identityKey);
                              }
                            }}
                          >
                            <PackageIcon className="size-4" />
                            {isInstallingSkill && !communityActionInstalled
                              ? t.settings.skills.installPending
                              : communityActionInstalled
                                ? t.settings.skills.installed
                                : t.settings.skills.installSkill}
                          </Button>
                        ) : null}
                        {canCreateMyVersion ? (
                          <Button
                            size="sm"
                            variant="outline"
                            disabled={downloadingSkillKey !== null}
                            onClick={() =>
                              void handleDownloadForkPackage(
                                skill,
                                display.identityKey,
                              )
                            }
                          >
                            <DownloadIcon className="size-4" />
                            {isDownloadingSkill
                              ? t.settings.skills.forkDownloadPending
                              : t.settings.skills.createMyVersion}
                          </Button>
                        ) : null}
                      </div>
                    ) : (
                      <div className="flex items-center gap-1">
                        {primaryActionText ? (
                          <Button
                            size="sm"
                            variant={
                              cardState.primaryAction === "publish" ||
                              cardState.primaryAction === "publish-update"
                                ? "default"
                                : "outline"
                            }
                            onClick={() => {
                              if (cardState.primaryAction === "view-update") {
                                setUpdateCandidate(skill);
                                return;
                              }
                              if (
                                cardState.primaryAction === "publish" ||
                                cardState.primaryAction === "publish-update"
                              ) {
                                setReleaseNotes("");
                                setPublishCandidate(skill);
                              }
                            }}
                          >
                            {primaryActionText}
                          </Button>
                        ) : null}
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-8 w-8"
                            >
                              <MoreVerticalIcon className="h-4 w-4" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuItem
                              onSelect={() => {
                                void handleDelete(skill);
                              }}
                            >
                              {t.common.delete}
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </div>
                    )}
                  </ItemActions>
                </Item>
              );
            })}
          </div>
        )}
      </div>

      <Dialog
        open={publishCandidate !== null}
        onOpenChange={(open) => {
          if (!open && !publishSkill.isPending) {
            setPublishCandidate(null);
            setReleaseNotes("");
          }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t.settings.skills.publishDialogTitle}</DialogTitle>
            <DialogDescription>
              {t.settings.skills.publishDialogDescription}
            </DialogDescription>
          </DialogHeader>
          {publishCandidate ? (
            <div className="space-y-4 text-sm">
              <div className="bg-muted/30 rounded-md border p-3">
                <div className="font-medium">{publishCandidate.name}</div>
                <div className="text-muted-foreground mt-1">
                  {getMySkillVersionDetail(publishCandidate)}
                </div>
              </div>
              <div>
                <div className="text-muted-foreground mb-1 text-xs font-medium tracking-wide uppercase">
                  {t.settings.skills.publishDescriptionLabel}
                </div>
                <p className="text-sm leading-6">
                  {publishCandidate.description}
                </p>
              </div>
              <div>
                <label
                  htmlFor="skill-release-notes"
                  className="text-muted-foreground mb-1 block text-xs font-medium tracking-wide uppercase"
                >
                  {t.settings.skills.releaseNotesLabel}
                </label>
                <textarea
                  id="skill-release-notes"
                  value={releaseNotes}
                  maxLength={4000}
                  disabled={publishSkill.isPending}
                  placeholder={t.settings.skills.releaseNotesPlaceholder}
                  onChange={(event) => setReleaseNotes(event.target.value)}
                  className="border-input bg-background ring-offset-background placeholder:text-muted-foreground focus-visible:ring-ring min-h-24 w-full rounded-md border px-3 py-2 text-sm focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50"
                />
                <p className="text-muted-foreground mt-1 text-xs">
                  {t.settings.skills.releaseNotesHelp}
                </p>
              </div>
              <div className="bg-muted/30 text-muted-foreground rounded-md border p-3">
                {t.settings.skills.publishAsLatestNotice}
              </div>
            </div>
          ) : null}
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              disabled={publishSkill.isPending}
              onClick={() => setPublishCandidate(null)}
            >
              {t.common.cancel}
            </Button>
            <Button
              type="button"
              disabled={publishSkill.isPending}
              onClick={() => void handlePublishConfirmed()}
            >
              {publishSkill.isPending
                ? t.settings.skills.publishPending
                : t.settings.skills.confirmPublish}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={updateCandidate !== null}
        onOpenChange={(open) => {
          if (!open && !confirmSkillUpdate.isPending) {
            setUpdateCandidate(null);
          }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t.settings.skills.updateDialogTitle}</DialogTitle>
            <DialogDescription>
              {t.settings.skills.updateDialogDescription}
            </DialogDescription>
          </DialogHeader>
          {updatePreview.isLoading ? (
            <div className="text-muted-foreground text-sm">
              {t.settings.skills.updatePreviewLoading}
            </div>
          ) : updatePreview.error ? (
            <div className="text-destructive text-sm">
              {updatePreview.error.message}
            </div>
          ) : updatePreview.data ? (
            <div className="space-y-4 text-sm">
              <div className="grid gap-3 rounded-md border p-3 sm:grid-cols-2">
                <div>
                  <div className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
                    {t.settings.skills.currentVersionLabel}
                  </div>
                  <div className="mt-1 font-medium">
                    {t.settings.skills.platformVersion(
                      updatePreview.data.current_platform_version,
                    )}
                  </div>
                </div>
                <div>
                  <div className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
                    {t.settings.skills.availableVersionLabel}
                  </div>
                  <div className="mt-1 font-medium">
                    {updatePreview.data.target_platform_version != null
                      ? t.settings.skills.platformVersion(
                          updatePreview.data.target_platform_version,
                        )
                      : t.settings.skills.noPlatformVersion}
                  </div>
                </div>
              </div>
              <div>
                <div className="text-muted-foreground mb-1 text-xs font-medium tracking-wide uppercase">
                  {t.settings.skills.releaseNotesLabel}
                </div>
                <p className="text-sm leading-6">
                  {updatePreview.data.release_notes ??
                    t.settings.skills.noReleaseNotes}
                </p>
              </div>
              <div className="grid gap-3 rounded-md border p-3 sm:grid-cols-3">
                <div>
                  <div className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
                    {t.settings.skills.sourceLabel}
                  </div>
                  <div className="mt-1">{updatePreview.data.source}</div>
                </div>
                <div>
                  <div className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
                    {t.settings.skills.publisherLabel}
                  </div>
                  <div className="mt-1">
                    {updatePreview.data.publisher ??
                      t.settings.skills.unknownPublisher}
                  </div>
                </div>
                <div>
                  <div className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
                    {t.settings.skills.publishedAtLabel}
                  </div>
                  <div className="mt-1">
                    {updatePreview.data.published_at ?? "-"}
                  </div>
                </div>
              </div>
              <div>
                <div className="text-muted-foreground mb-1 text-xs font-medium tracking-wide uppercase">
                  {t.settings.skills.affectedAgentsLabel}
                </div>
                <p className="text-sm leading-6">
                  {getAffectedAgentsText(
                    updatePreview.data.affected_agents.map(
                      (agent) => agent.name,
                    ),
                  )}
                </p>
              </div>
              {updatePreview.data.status !== "available" ? (
                <div className="bg-muted/30 text-muted-foreground rounded-md border p-3">
                  {updatePreview.data.message}
                </div>
              ) : null}
            </div>
          ) : null}
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              disabled={updateDialogState.cancelDisabled}
              onClick={() => setUpdateCandidate(null)}
            >
              {t.common.cancel}
            </Button>
            <Button
              type="button"
              disabled={updateDialogState.confirmDisabled}
              onClick={() => void handleUpdateConfirmed()}
            >
              {confirmSkillUpdate.isPending
                ? t.settings.skills.updatePending
                : t.settings.skills.confirmUpdate}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function SkillGalleryEmptyState({
  content,
  isUploadPending,
  onBrowseCommunity,
  onClearSearch,
  onUpload,
}: {
  content: SkillGalleryEmptyContent;
  isUploadPending: boolean;
  onBrowseCommunity: () => void;
  onClearSearch: () => void;
  onUpload: () => void;
}) {
  const { t } = useI18n();

  return (
    <Empty className="bg-muted/10 mt-6 min-h-72 border">
      <EmptyHeader>
        <EmptyMedia variant="icon">
          {content.icon === "search" ? <SearchIcon /> : <PackageIcon />}
        </EmptyMedia>
        <EmptyTitle>{content.title}</EmptyTitle>
        <EmptyDescription>{content.description}</EmptyDescription>
      </EmptyHeader>
      {content.action ? (
        <EmptyContent>
          {content.action === "clear-search" ? (
            <Button variant="outline" onClick={onClearSearch}>
              {t.settings.skills.clearSearch}
            </Button>
          ) : content.action === "browse-community" ? (
            <Button variant="outline" onClick={onBrowseCommunity}>
              {t.settings.skills.browseCommunitySkills}
            </Button>
          ) : (
            <Button onClick={onUpload} disabled={isUploadPending}>
              <UploadIcon className="size-4" />
              {isUploadPending
                ? t.settings.skills.uploadPending
                : t.settings.skills.uploadSkill}
            </Button>
          )}
        </EmptyContent>
      ) : null}
    </Empty>
  );
}

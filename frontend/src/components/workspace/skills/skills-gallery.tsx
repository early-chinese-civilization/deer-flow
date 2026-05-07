"use client";

import { MoreVerticalIcon, UploadIcon } from "lucide-react";
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
  useInstallSkillHubSkill,
  usePublishSkill,
  usePreviewSkillInstallUpdate,
  useSkills,
  useUploadSkills,
} from "@/core/skills";
import {
  findInstalledSkillForSkillHubItem,
  getInstalledPlatformVersion,
  getSkillDisplayContract,
  getSkillHubLatestPlatformVersion,
  getSkillInstallState,
  getSkillPlatformVersion,
  getSkillWorkspaceCardState,
  isAuthoredSkillRelation,
  isCommunitySkill,
  isPersonalSkill,
  skillMatchesWorkspaceSegment,
  type SkillInstallState,
  type SkillWorkspacePrimaryAction,
  type SkillWorkspaceSegment,
} from "@/core/skills/display";
import type { Skill } from "@/core/skills/type";

type SkillsSurface = "community" | "personal";

const SKILL_SURFACE_SEGMENTS: Record<SkillsSurface, SkillWorkspaceSegment[]> = {
  community: ["all", "downloaded", "published", "updates"],
  personal: ["all", "downloaded", "authored", "published", "updates", "forks"],
};

export function SkillsGallery() {
  const { t } = useI18n();
  const { skills, isLoading, error } = useSkills();
  const deleteSkill = useDeleteSkill();
  const installSkillHubSkill = useInstallSkillHubSkill();
  const confirmSkillUpdate = useConfirmSkillInstallUpdate();
  const publishSkill = usePublishSkill();
  const uploadSkills = useUploadSkills();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [surface, setSurface] = useState<SkillsSurface>("community");
  const [segment, setSegment] = useState<SkillWorkspaceSegment>("all");
  const [publishCandidate, setPublishCandidate] = useState<Skill | null>(null);
  const [updateCandidate, setUpdateCandidate] = useState<Skill | null>(null);
  const [releaseNotes, setReleaseNotes] = useState("");
  const updatePreview = usePreviewSkillInstallUpdate(
    updateCandidate?.name ?? null,
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
    const inSurface =
      surface === "community"
        ? isCommunitySkill(skill)
        : isPersonalSkill(skill);
    return (
      inSurface && skillMatchesWorkspaceSegment(skill, segment, installedSkill)
    );
  });

  function getVersionText(version: number | null) {
    if (version != null) {
      return t.settings.skills.platformVersion(version);
    }
    return t.settings.skills.noPlatformVersion;
  }

  function getSkillHubVersionDetail(skill: Skill) {
    const installedSkill = findInstalledSkillForSkillHubItem(skill, skills);
    const installedVersion = getInstalledPlatformVersion(skill, installedSkill);
    const latestVersion = getSkillHubLatestPlatformVersion(skill);

    if (installedVersion != null && latestVersion != null) {
      if (latestVersion > installedVersion) {
        return t.settings.skills.currentAndUpdateVersions(
          installedVersion,
          latestVersion,
        );
      }
      return t.settings.skills.currentVersion(installedVersion);
    }

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
      return t.settings.skills.downloadedSource(
        skill.owner_display_name ?? t.settings.skills.communitySpaceSource,
      );
    }
    if (display.viewerRelation === "forked") {
      return skill.owner_display_name
        ? t.settings.skills.forkedSource(skill.owner_display_name)
        : t.settings.skills.forkedSkill;
    }
    return t.settings.skills.createdSource;
  }

  function getSegmentText(value: SkillWorkspaceSegment) {
    switch (value) {
      case "downloaded":
        return t.settings.skills.downloadedSegment;
      case "authored":
        return t.settings.skills.authoredSegment;
      case "published":
        return t.settings.skills.publishedSegment;
      case "updates":
        return t.settings.skills.updatesSegment;
      case "forks":
        return t.settings.skills.forksSegment;
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
    if (
      display.viewerRelation === "authored_published" ||
      action === "manage-published" ||
      action === "manage-owned"
    ) {
      return t.settings.skills.published;
    }
    if (display.viewerRelation === "forked") {
      return t.settings.skills.forkedSkill;
    }
    if (display.space === "personal" && display.viewerRelation === "authored") {
      return t.settings.skills.mySkill;
    }
    if (action === "view-update" || installState === "update-available") {
      return t.settings.skills.updateAvailable;
    }
    if (action === "view-personal" || display.viewerRelation === "downloaded") {
      return t.settings.skills.downloadedToPersonal;
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
      case "manage-published":
      case "manage-owned":
        return t.settings.skills.managePublished;
      case "publish":
        return t.settings.skills.publishSkill;
      case "publish-update":
        return t.settings.skills.publishUpdate;
      case "none":
        return null;
    }
  }

  function moveToPersonalSpace(nextSegment: SkillWorkspaceSegment) {
    setSurface("personal");
    setSegment(nextSegment);
  }

  function getAffectedAgentsText(agentNames: string[]) {
    if (agentNames.length === 0) {
      return t.settings.skills.noAffectedAgents;
    }
    return agentNames.join(", ");
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

  async function handleInstall(skill: Skill) {
    try {
      const result = await checkSkillHubInstall(skill.name, {
        owner_user_id: skill.owner_user_id ?? null,
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
        overwrite,
      });
      toast.success(t.settings.skills.installSuccess(skill.name));
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : t.settings.skills.installError,
      );
    }
  }

  async function handleUpdateConfirmed() {
    if (!updateCandidate || !updatePreview.data?.target_skill_version_id) {
      return;
    }

    try {
      await confirmSkillUpdate.mutateAsync({
        skillName: updateCandidate.name,
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
              <TabsTrigger value="community">
                {t.settings.skills.communitySpaceTab}
              </TabsTrigger>
              <TabsTrigger value="personal">
                {t.settings.skills.personalSpaceTab}
              </TabsTrigger>
            </TabsList>
          </Tabs>
        </div>
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

        {isLoading ? (
          <div className="text-muted-foreground text-sm">
            {t.common.loading}
          </div>
        ) : error ? (
          <div className="text-destructive text-sm">{error.message}</div>
        ) : filteredSkills.length === 0 ? (
          <div className="text-muted-foreground text-sm">
            {surface === "community"
              ? t.settings.skills.noSkillHubSkills
              : t.settings.skills.noMySkills}
          </div>
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
              const canPublishSkill = isAuthoredSkillRelation(skill);
              const platformVersion =
                display.space === "community"
                  ? getSkillHubLatestPlatformVersion(skill)
                  : getSkillPlatformVersion(skill);
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
                    </div>
                    <div className="text-muted-foreground mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
                      <span>
                        {display.space === "community"
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
                    {display.space === "community" ? (
                      <Button
                        size="sm"
                        variant={
                          cardState.primaryAction === "add-to-personal"
                            ? "default"
                            : "outline"
                        }
                        disabled={
                          installSkillHubSkill.isPending &&
                          cardState.primaryAction === "add-to-personal"
                        }
                        onClick={() => {
                          if (cardState.primaryAction === "manage-published") {
                            moveToPersonalSpace("published");
                            return;
                          }
                          if (cardState.primaryAction === "view-personal") {
                            moveToPersonalSpace("downloaded");
                            return;
                          }
                          if (cardState.primaryAction === "view-update") {
                            setUpdateCandidate(installedSkill ?? skill);
                            return;
                          }
                          void handleInstall(skill);
                        }}
                      >
                        {installSkillHubSkill.isPending &&
                        cardState.primaryAction === "add-to-personal"
                          ? t.settings.skills.installPending
                          : primaryActionText}
                      </Button>
                    ) : (
                      <div className="flex items-center gap-1">
                        {primaryActionText ? (
                          <Button
                            size="sm"
                            disabled={
                              cardState.primaryAction === "manage-owned"
                            }
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
                            {installState === "update-available" ? (
                              <DropdownMenuItem
                                onSelect={() => {
                                  setUpdateCandidate(skill);
                                }}
                              >
                                {t.settings.skills.viewUpdate}
                              </DropdownMenuItem>
                            ) : null}
                            {canPublishSkill ? (
                              <DropdownMenuItem
                                onSelect={() => {
                                  setReleaseNotes("");
                                  setPublishCandidate(skill);
                                }}
                              >
                                {cardState.primaryAction === "publish-update"
                                  ? t.settings.skills.publishUpdate
                                  : t.settings.skills.publishSkill}
                              </DropdownMenuItem>
                            ) : null}
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

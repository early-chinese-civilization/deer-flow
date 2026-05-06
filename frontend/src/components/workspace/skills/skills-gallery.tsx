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
  getSkillHubLatestPlatformVersion,
  getSkillInstallState,
  getSkillPlatformVersion,
  type SkillInstallState,
} from "@/core/skills/display";
import type { Skill } from "@/core/skills/type";

type SkillsSurface = "skillhub" | "my-skills";

export function SkillsGallery() {
  const { t } = useI18n();
  const { skills, isLoading, error } = useSkills();
  const deleteSkill = useDeleteSkill();
  const installSkillHubSkill = useInstallSkillHubSkill();
  const confirmSkillUpdate = useConfirmSkillInstallUpdate();
  const publishSkill = usePublishSkill();
  const uploadSkills = useUploadSkills();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [filter, setFilter] = useState<SkillsSurface>("skillhub");
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

  const filteredSkills = skills.filter((skill) =>
    filter === "skillhub"
      ? skill.category === "public"
      : skill.category === "custom",
  );

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
    if (skill.category === "public") {
      return skill.owner_display_name
        ? t.settings.skills.communitySource(skill.owner_display_name)
        : t.settings.skills.officialSource;
    }
    if (skill.skill_install_id != null) {
      return t.settings.skills.installedSource;
    }
    return t.settings.skills.createdSource;
  }

  function getInstallStateText(state: SkillInstallState) {
    if (state === "update-available") {
      return t.settings.skills.updateAvailable;
    }
    if (state === "installed") {
      return t.settings.skills.installed;
    }
    return t.settings.skills.notInstalled;
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
        error instanceof Error
          ? error.message
          : t.settings.skills.updateError,
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
            defaultValue="skillhub"
            onValueChange={(value) => setFilter(value as SkillsSurface)}
          >
            <TabsList variant="line">
              <TabsTrigger value="skillhub">
                {t.settings.skills.skillHubTab}
              </TabsTrigger>
              <TabsTrigger value="my-skills">
                {t.settings.skills.mySkillsTab}
              </TabsTrigger>
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
            {filter === "skillhub"
              ? t.settings.skills.noSkillHubSkills
              : t.settings.skills.noMySkills}
          </div>
        ) : (
          <div className="space-y-4">
            {filteredSkills.map((skill) => {
              const installedSkill = findInstalledSkillForSkillHubItem(
                skill,
                skills,
              );
              const installState = getSkillInstallState(skill, installedSkill);
              const platformVersion =
                skill.category === "public"
                  ? getSkillHubLatestPlatformVersion(skill)
                  : getSkillPlatformVersion(skill);
              const isInstallDisabled =
                (installState !== "not-installed" &&
                  installState !== "update-available") ||
                installSkillHubSkill.isPending;

              return (
                <Item
                  key={`${skill.category}-${skill.name}-${skill.owner_user_id ?? "system"}`}
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
                        {skill.category === "public"
                          ? getInstallStateText(installState)
                          : installState === "update-available"
                            ? t.settings.skills.updateAvailable
                            : skill.release_status === "published"
                              ? t.settings.skills.published
                              : t.settings.skills.unpublished}
                      </Badge>
                    </div>
                    <div className="text-muted-foreground mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
                      <span>
                        {skill.category === "public"
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
                    {skill.category === "public" ? (
                      <Button
                        size="sm"
                        variant={
                          installState === "not-installed"
                            ? "default"
                            : "outline"
                        }
                        disabled={isInstallDisabled}
                        onClick={() => {
                          if (installState === "update-available") {
                            setUpdateCandidate(installedSkill ?? skill);
                            return;
                          }
                          void handleInstall(skill);
                        }}
                      >
                        {installSkillHubSkill.isPending
                          ? t.settings.skills.installPending
                          : installState === "not-installed"
                            ? t.settings.skills.installSkill
                            : getInstallStateText(installState)}
                      </Button>
                    ) : (
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
                          <DropdownMenuItem
                            onSelect={() => {
                              setReleaseNotes("");
                              setPublishCandidate(skill);
                            }}
                          >
                            {t.settings.skills.publishSkill}
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
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

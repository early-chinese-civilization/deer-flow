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
import { checkSkillDownload, checkSkillUpload } from "@/core/skills";
import {
  useDeleteSkill,
  useDownloadSkill,
  usePublishSkill,
  useSkills,
  useUploadSkills,
} from "@/core/skills";
import type { Skill } from "@/core/skills/type";

export function SkillsGallery() {
  const { t } = useI18n();
  const { skills, isLoading, error } = useSkills();
  const deleteSkill = useDeleteSkill();
  const downloadSkill = useDownloadSkill();
  const publishSkill = usePublishSkill();
  const uploadSkills = useUploadSkills();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [filter, setFilter] = useState<Skill["category"]>("public");
  const [publishCandidate, setPublishCandidate] = useState<Skill | null>(null);
  const [releaseNotes, setReleaseNotes] = useState("");

  const filteredSkills = skills.filter((skill) => skill.category === filter);

  function getDisplayVersion(skill: Skill) {
    return skill.package_version ?? skill.release_version ?? null;
  }

  function getVersionText(skill: Skill) {
    const displayVersion = getDisplayVersion(skill);
    if (displayVersion) {
      return displayVersion;
    }
    return t.settings.skills.noPackageVersion;
  }

  function getVersionDetail(skill: Skill) {
    const displayVersion = getDisplayVersion(skill);
    if (skill.category === "public") {
      return displayVersion
        ? t.settings.skills.latestVersion(displayVersion)
        : t.settings.skills.noPackageVersion;
    }
    return skill.package_version
      ? t.settings.skills.packageVersion(skill.package_version)
      : t.settings.skills.noPackageVersion;
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

  async function handleDownload(skill: Skill) {
    try {
      const result = await checkSkillDownload(skill.name, {
        owner_user_id: skill.owner_user_id ?? null,
      });
      const overwrite = result.exists
        ? window.confirm(t.settings.skills.conflictConfirm(result.skill_name))
        : false;

      if (result.exists && !overwrite) {
        return;
      }

      await downloadSkill.mutateAsync({
        skillName: skill.name,
        ownerUserId: skill.owner_user_id ?? null,
        overwrite,
      });
      toast.success(t.settings.skills.downloadSuccess(skill.name));
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : t.settings.skills.uploadError,
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
          <Tabs defaultValue="public" onValueChange={(value) => setFilter(value as Skill["category"])}>
            <TabsList variant="line">
              <TabsTrigger value="public">{t.common.public}</TabsTrigger>
              <TabsTrigger value="custom">{t.common.custom}</TabsTrigger>
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
            {filter === "public"
              ? t.settings.skills.noPublicSkills
              : t.settings.skills.noCustomSkills}
          </div>
        ) : (
          <div className="space-y-4">
            {filteredSkills.map((skill) => (
              <Item
                key={`${skill.category}-${skill.name}-${skill.owner_user_id ?? "system"}`}
                className="w-full"
                variant="outline"
              >
                <ItemContent>
                  <div className="flex flex-wrap items-center gap-2">
                    <ItemTitle>{skill.name}</ItemTitle>
                    <Badge variant={getDisplayVersion(skill) ? "secondary" : "outline"}>
                      {getVersionText(skill)}
                    </Badge>
                  </div>
                  <div className="text-muted-foreground mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
                    <span>{getVersionDetail(skill)}</span>
                    {skill.category === "public" && skill.owner_display_name ? (
                      <span>
                        {t.settings.skills.publishedBy(skill.owner_display_name)}
                      </span>
                    ) : null}
                  </div>
                  <ItemDescription className="line-clamp-4">
                    {skill.description}
                  </ItemDescription>
                </ItemContent>
                <ItemActions>
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button variant="ghost" size="icon" className="h-8 w-8">
                        <MoreVerticalIcon className="h-4 w-4" />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      {skill.category === "public" ? (
                        <DropdownMenuItem
                          onSelect={() => {
                            void handleDownload(skill);
                          }}
                        >
                          {t.settings.skills.downloadSkill}
                        </DropdownMenuItem>
                      ) : (
                        <>
                          <DropdownMenuItem
                            onSelect={() => {
                              void handleDelete(skill);
                            }}
                          >
                            {t.common.delete}
                          </DropdownMenuItem>
                          <DropdownMenuItem
                            onSelect={() => {
                              setReleaseNotes("");
                              setPublishCandidate(skill);
                            }}
                          >
                            {t.settings.skills.publishSkill}
                          </DropdownMenuItem>
                        </>
                      )}
                    </DropdownMenuContent>
                  </DropdownMenu>
                </ItemActions>
              </Item>
            ))}
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
              <div className="rounded-md border bg-muted/30 p-3">
                <div className="font-medium">{publishCandidate.name}</div>
                <div className="text-muted-foreground mt-1">
                  {getVersionDetail(publishCandidate)}
                </div>
              </div>
              <div>
                <div className="text-muted-foreground mb-1 text-xs font-medium uppercase tracking-wide">
                  {t.settings.skills.publishDescriptionLabel}
                </div>
                <p className="text-sm leading-6">{publishCandidate.description}</p>
              </div>
              <div>
                <label
                  htmlFor="skill-release-notes"
                  className="text-muted-foreground mb-1 block text-xs font-medium uppercase tracking-wide"
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
              <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-200">
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
    </div>
  );
}

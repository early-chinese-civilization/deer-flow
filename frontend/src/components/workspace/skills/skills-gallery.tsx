"use client";

import {
  MoreVerticalIcon,
  UploadIcon,
} from "lucide-react";
import { type ChangeEvent, useRef, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
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
import { checkSkillDownload, checkSkillUpload } from "@/core/skills";
import { useDeleteSkill, useDownloadSkill, usePublishSkill, useSkills, useUploadSkills } from "@/core/skills";
import type { Skill } from "@/core/skills/type";
import { useI18n } from "@/core/i18n/hooks";

export function SkillsGallery() {
  const { t } = useI18n();
  const { skills, isLoading, error } = useSkills();
  const deleteSkill = useDeleteSkill();
  const downloadSkill = useDownloadSkill();
  const publishSkill = usePublishSkill();
  const uploadSkills = useUploadSkills();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [filter, setFilter] = useState<string>("public");

  const filteredSkills = skills.filter((skill) => skill.category === filter);

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
      const match = message.match(/agent '([^']+)'/);
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
      toast.error(error instanceof Error ? error.message : t.settings.skills.uploadError);
    }
  }

  async function handlePublish(skill: Skill) {
    try {
      await publishSkill.mutateAsync(skill.name);
      toast.success(t.settings.skills.publishSuccess(skill.name));
    } catch (error) {
      toast.error(error instanceof Error ? error.message : t.settings.skills.uploadError);
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
        toast.error(error instanceof Error ? error.message : t.settings.skills.uploadError);
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
      toast.error(error instanceof Error ? error.message : t.settings.skills.uploadError);
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
          <Tabs defaultValue="public" onValueChange={setFilter}>
            <TabsList variant="line">
              <TabsTrigger value="public">{t.common.public}</TabsTrigger>
              <TabsTrigger value="custom">{t.common.custom}</TabsTrigger>
            </TabsList>
          </Tabs>
        </div>

        {isLoading ? (
          <div className="text-muted-foreground text-sm">{t.common.loading}</div>
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
                  <ItemTitle>{skill.name}</ItemTitle>
                  {skill.category === "public" && skill.owner_display_name ? (
                    <div className="text-muted-foreground text-xs">
                      {t.settings.skills.publishedBy(skill.owner_display_name)}
                    </div>
                  ) : null}
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
                              void handlePublish(skill);
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
    </div>
  );
}

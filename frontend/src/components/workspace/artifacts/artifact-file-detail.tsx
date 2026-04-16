import {
  AlertCircleIcon,
  Code2Icon,
  CopyIcon,
  DownloadIcon,
  EyeIcon,
  LoaderIcon,
  PackageIcon,
  SquareArrowOutUpRightIcon,
  XIcon,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Streamdown } from "streamdown";

import {
  Artifact,
  ArtifactAction,
  ArtifactActions,
  ArtifactContent,
  ArtifactHeader,
  ArtifactTitle,
} from "@/components/ai-elements/artifact";
import { Button } from "@/components/ui/button";
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty";
import { Select, SelectItem } from "@/components/ui/select";
import {
  SelectContent,
  SelectGroup,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { CodeEditor } from "@/components/workspace/code-editor";
import { getArtifactDisplayMode } from "@/core/artifacts/display";
import { useArtifactContent } from "@/core/artifacts/hooks";
import { urlOfArtifact } from "@/core/artifacts/utils";
import { useI18n } from "@/core/i18n/hooks";
import { installSkill } from "@/core/skills/api";
import { streamdownPlugins } from "@/core/streamdown";
import {
  checkCodeFile,
  getFileExtensionDisplayName,
  getFileName,
} from "@/core/utils/files";
import { env } from "@/env";
import { cn } from "@/lib/utils";

import { ArtifactLink } from "../citations/artifact-link";
import { useThread } from "../messages/context";
import { Tooltip } from "../tooltip";

import { useArtifacts } from "./context";

export function ArtifactFileDetail({
  className,
  filepath: filepathFromProps,
  threadId,
}: {
  className?: string;
  filepath: string;
  threadId: string;
}) {
  const { t } = useI18n();
  const { artifacts, deselect, select } = useArtifacts();
  const isWriteFile = useMemo(() => {
    return filepathFromProps.startsWith("write-file:");
  }, [filepathFromProps]);
  const filepath = useMemo(() => {
    if (isWriteFile) {
      const url = new URL(filepathFromProps);
      return decodeURIComponent(url.pathname);
    }
    return filepathFromProps;
  }, [filepathFromProps, isWriteFile]);
  const isSkillFile = useMemo(() => {
    return filepath.endsWith(".skill");
  }, [filepath]);
  const { isCodeFile, language } = useMemo(() => {
    if (isWriteFile) {
      let nextLanguage = checkCodeFile(filepath).language;
      nextLanguage ??= "text";
      return { isCodeFile: true, language: nextLanguage };
    }
    if (isSkillFile) {
      return { isCodeFile: true, language: "markdown" };
    }
    return checkCodeFile(filepath);
  }, [filepath, isWriteFile, isSkillFile]);
  const displayMode = useMemo(() => {
    if (isCodeFile) {
      return language === "html" || language === "markdown"
        ? "rich-preview"
        : "code";
    }

    return getArtifactDisplayMode(filepath);
  }, [filepath, isCodeFile, language]);
  const isSupportPreview = useMemo(() => {
    return displayMode === "rich-preview";
  }, [displayMode]);
  const { content, url } = useArtifactContent({
    threadId,
    filepath: filepathFromProps,
    enabled: isCodeFile && !isWriteFile,
  });

  const displayContent = content ?? "";

  const [viewMode, setViewMode] = useState<"code" | "preview">("code");
  const [isInstalling, setIsInstalling] = useState(false);
  const { isMock } = useThread();
  useEffect(() => {
    if (isSupportPreview) {
      setViewMode("preview");
      return;
    }

    setViewMode("code");
  }, [isSupportPreview]);

  const handleInstallSkill = useCallback(async () => {
    if (isInstalling) return;

    setIsInstalling(true);
    try {
      const result = await installSkill({
        thread_id: threadId,
        path: filepath,
      });
      if (result.success) {
        toast.success(result.message);
        return;
      }

      toast.error(result.message ?? "Failed to install skill");
    } catch (error) {
      console.error("Failed to install skill:", error);
      toast.error("Failed to install skill");
    } finally {
      setIsInstalling(false);
    }
  }, [filepath, isInstalling, threadId]);

  return (
    <Artifact className={cn(className)}>
      <ArtifactHeader className="px-2">
        <div className="flex items-center gap-2">
          <ArtifactTitle>
            {isWriteFile ? (
              <div className="px-2">{getFileName(filepath)}</div>
            ) : (
              <Select value={filepath} onValueChange={select}>
                <SelectTrigger className="border-none bg-transparent! shadow-none select-none focus:outline-0 active:outline-0">
                  <SelectValue placeholder="Select a file" />
                </SelectTrigger>
                <SelectContent className="select-none">
                  <SelectGroup>
                    {(artifacts ?? []).map((artifactPath) => (
                      <SelectItem key={artifactPath} value={artifactPath}>
                        {getFileName(artifactPath)}
                      </SelectItem>
                    ))}
                  </SelectGroup>
                </SelectContent>
              </Select>
            )}
          </ArtifactTitle>
        </div>
        <div className="flex min-w-0 grow items-center justify-center">
          {isSupportPreview && (
            <ToggleGroup
              className="mx-auto"
              type="single"
              variant="outline"
              size="sm"
              value={viewMode}
              onValueChange={(value) => {
                if (value) {
                  setViewMode(value as "code" | "preview");
                }
              }}
            >
              <ToggleGroupItem value="code">
                <Code2Icon />
              </ToggleGroupItem>
              <ToggleGroupItem value="preview">
                <EyeIcon />
              </ToggleGroupItem>
            </ToggleGroup>
          )}
        </div>
        <div className="flex items-center gap-2">
          <ArtifactActions>
            {!isWriteFile && filepath.endsWith(".skill") && (
              <Tooltip content={t.toolCalls.skillInstallTooltip}>
                <ArtifactAction
                  icon={isInstalling ? LoaderIcon : PackageIcon}
                  label={t.common.install}
                  tooltip={t.common.install}
                  disabled={
                    isInstalling ||
                    env.NEXT_PUBLIC_STATIC_WEBSITE_ONLY === "true"
                  }
                  onClick={handleInstallSkill}
                />
              </Tooltip>
            )}
            {!isWriteFile && (
              <a
                href={urlOfArtifact({ filepath, threadId })}
                target="_blank"
                rel="noopener noreferrer"
              >
                <ArtifactAction
                  icon={SquareArrowOutUpRightIcon}
                  label={t.common.openInNewWindow}
                  tooltip={t.common.openInNewWindow}
                />
              </a>
            )}
            {isCodeFile && (
              <ArtifactAction
                icon={CopyIcon}
                label={t.clipboard.copyToClipboard}
                disabled={!content}
                onClick={async () => {
                  try {
                    await navigator.clipboard.writeText(displayContent ?? "");
                    toast.success(t.clipboard.copiedToClipboard);
                  } catch (error) {
                    toast.error("Failed to copy to clipboard");
                    console.error(error);
                  }
                }}
                tooltip={t.clipboard.copyToClipboard}
              />
            )}
            {!isWriteFile && (
              <a
                href={urlOfArtifact({ filepath, threadId, download: true })}
                target="_blank"
                rel="noopener noreferrer"
              >
                <ArtifactAction
                  icon={DownloadIcon}
                  label={t.common.download}
                  tooltip={t.common.download}
                />
              </a>
            )}
            <ArtifactAction
              icon={XIcon}
              label={t.common.close}
              onClick={deselect}
              tooltip={t.common.close}
            />
          </ArtifactActions>
        </div>
      </ArtifactHeader>
      <ArtifactContent className="p-0">
        {isSupportPreview &&
          viewMode === "preview" &&
          (language === "markdown" || language === "html") && (
            <ArtifactFilePreview
              content={displayContent}
              isWriteFile={isWriteFile}
              language={language ?? "text"}
              url={url}
            />
          )}
        {isCodeFile && viewMode === "code" && (
          <CodeEditor
            className="size-full resize-none rounded-none border-none"
            value={displayContent ?? ""}
            readonly
          />
        )}
        {displayMode === "iframe-preview" && (
          <iframe
            className="size-full"
            src={urlOfArtifact({ filepath, threadId, isMock })}
          />
        )}
        {displayMode === "unsupported-preview" && (
          <ArtifactUnsupportedPreview
            downloadUrl={urlOfArtifact({
              filepath,
              threadId,
              isMock,
              download: true,
            })}
            fileType={getFileExtensionDisplayName(filepath)}
          />
        )}
      </ArtifactContent>
    </Artifact>
  );
}

function ArtifactUnsupportedPreview({
  downloadUrl,
  fileType,
}: {
  downloadUrl: string;
  fileType: string;
}) {
  const { t } = useI18n();

  return (
    <Empty className="border-0 rounded-none">
      <EmptyHeader>
        <EmptyMedia variant="icon">
          <AlertCircleIcon />
        </EmptyMedia>
        <EmptyTitle>{t.artifacts.previewUnavailable}</EmptyTitle>
        <EmptyDescription>
          {t.artifacts.previewUnavailableDescription(fileType)}
        </EmptyDescription>
      </EmptyHeader>
      <EmptyContent>
        <Button asChild variant="outline">
          <a href={downloadUrl} target="_blank" rel="noopener noreferrer">
            <DownloadIcon />
            {t.artifacts.downloadFile}
          </a>
        </Button>
      </EmptyContent>
    </Empty>
  );
}

export function ArtifactFilePreview({
  content,
  isWriteFile,
  language,
  url,
}: {
  content: string;
  isWriteFile: boolean;
  language: string;
  url?: string;
}) {
  if (language === "markdown") {
    return (
      <div className="size-full px-4">
        <Streamdown
          className="size-full"
          {...streamdownPlugins}
          components={{ a: ArtifactLink }}
        >
          {content ?? ""}
        </Streamdown>
      </div>
    );
  }
  if (language === "html") {
    return (
      <iframe
        className="size-full"
        title="Artifact preview"
        sandbox="allow-scripts allow-forms"
        {...(isWriteFile ? { srcDoc: content } : url ? { src: url } : {})}
      />
    );
  }
  return null;
}

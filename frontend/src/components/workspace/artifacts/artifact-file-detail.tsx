import {
  AlertCircleIcon,
  Code2Icon,
  CopyIcon,
  EyeIcon,
  XIcon,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
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
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { CodeEditor } from "@/components/workspace/code-editor";
import { getArtifactDisplayMode } from "@/core/artifacts/display";
import { useArtifactContent } from "@/core/artifacts/hooks";
import { urlOfArtifact } from "@/core/artifacts/utils";
import { useI18n } from "@/core/i18n/hooks";
import { useResolvedOssUrl } from "@/core/oss";
import { streamdownPlugins } from "@/core/streamdown";
import {
  checkCodeFile,
  getFileExtensionDisplayName,
  getFileName,
} from "@/core/utils/files";
import { cn } from "@/lib/utils";

import { ArtifactLink } from "../citations/artifact-link";
import { useThread } from "../messages/context";

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
  const { deselect, getArtifactSource } = useArtifacts();
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
  const artifactSource = useMemo(() => {
    if (isWriteFile) {
      return null;
    }
    return getArtifactSource(threadId, filepath);
  }, [filepath, getArtifactSource, isWriteFile, threadId]);
  const { isMock, workspaceId } = useThread();
  const browserOssSource = artifactSource?.browserOssSource ?? null;
  const { data: resolvedOssUrl } = useResolvedOssUrl(
    workspaceId,
    browserOssSource,
  );
  const hasResolvedBrowserOssUrl = !browserOssSource || Boolean(resolvedOssUrl);
  const artifactViewUrl = browserOssSource
    ? resolvedOssUrl
    : urlOfArtifact({ filepath, threadId, isMock });
  const { content, url } = useArtifactContent({
    threadId,
    filepath: filepathFromProps,
    enabled: isCodeFile && !isWriteFile && hasResolvedBrowserOssUrl,
    urlOverride: browserOssSource ? resolvedOssUrl : undefined,
  });

  const displayContent = content ?? "";

  const [viewMode, setViewMode] = useState<"code" | "preview">("code");
  useEffect(() => {
    if (isSupportPreview) {
      setViewMode("preview");
      return;
    }

    setViewMode("code");
  }, [isSupportPreview]);

  return (
    <Artifact className={cn(className)}>
      <ArtifactHeader className="px-2">
        <div className="flex items-center gap-2">
          <ArtifactTitle>
            <div className="px-2">{getFileName(filepath)}</div>
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
        {displayMode === "image-preview" && hasResolvedBrowserOssUrl && (
          <div className="flex size-full items-center justify-center bg-black/5 p-4">
            <img
              className="max-h-full max-w-full rounded-md object-contain"
              src={artifactViewUrl}
              alt={getFileName(filepath)}
            />
          </div>
        )}
        {displayMode === "iframe-preview" && hasResolvedBrowserOssUrl && (
          <iframe className="size-full" src={artifactViewUrl} />
        )}
        {displayMode === "unsupported-preview" && (
          <ArtifactUnsupportedPreview
            fileType={getFileExtensionDisplayName(filepath)}
          />
        )}
      </ArtifactContent>
    </Artifact>
  );
}

function ArtifactUnsupportedPreview({ fileType }: { fileType: string }) {
  const { t } = useI18n();

  return (
    <Empty className="rounded-none border-0">
      <EmptyHeader>
        <EmptyMedia variant="icon">
          <AlertCircleIcon />
        </EmptyMedia>
        <EmptyTitle>{t.artifacts.previewUnavailable}</EmptyTitle>
        <EmptyDescription>
          {t.artifacts.previewUnavailableDescription(fileType)}
        </EmptyDescription>
      </EmptyHeader>
      <EmptyContent />
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

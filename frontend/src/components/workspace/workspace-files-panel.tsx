"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertCircleIcon, RefreshCwIcon, SearchIcon } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  InputGroup,
  InputGroupAddon,
  InputGroupInput,
} from "@/components/ui/input-group";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { getThread } from "@/core/threads/api";
import { listUploadedFiles, type UploadedFileInfo } from "@/core/uploads";
import { getFileIcon } from "@/core/utils/files";
import { cn } from "@/lib/utils";

import { useArtifacts } from "./artifacts/context";

function formatBytes(bytes: number): string {
  if (bytes <= 0) {
    return "--";
  }

  if (bytes < 1024) {
    return `${bytes} B`;
  }

  const kilobytes = bytes / 1024;
  if (kilobytes < 1024) {
    return `${kilobytes.toFixed(1)} KB`;
  }

  return `${(kilobytes / 1024).toFixed(1)} MB`;
}

function formatModifiedTime(modified?: number): string {
  if (!modified) {
    return "刚刚更新";
  }

  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(modified * 1000));
}

function WorkspaceFilesLoading() {
  return (
    <div className="space-y-2 pr-2">
      {Array.from({ length: 6 }).map((_, index) => (
        <div
          key={`workspace-file-skeleton-${index}`}
          className="border-border/50 rounded-lg border px-3 py-3"
        >
          <Skeleton className="h-4 w-2/3" />
          <Skeleton className="mt-2 h-3 w-1/3" />
        </div>
      ))}
    </div>
  );
}

function WorkspaceFilesEmpty({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <div className="text-muted-foreground flex min-h-48 flex-col items-center justify-center gap-3 px-4 text-center">
      <AlertCircleIcon className="size-5" />
      <div>
        <div className="text-foreground text-sm font-medium">{title}</div>
        <p className="mt-1 text-xs leading-5">{description}</p>
      </div>
    </div>
  );
}

function WorkspaceFileRow({
  file,
  selected,
  onSelect,
}: {
  file: UploadedFileInfo;
  selected: boolean;
  onSelect: (file: UploadedFileInfo) => void;
}) {
  return (
    <button
      type="button"
      className={cn(
        "border-border/50 hover:bg-accent/70 flex w-full items-start gap-3 rounded-lg border px-3 py-3 text-left transition-colors",
        selected && "bg-accent border-border",
      )}
      onClick={() => onSelect(file)}
    >
      <span className="text-muted-foreground mt-0.5 shrink-0">
        {getFileIcon(file.filename, "size-4")}
      </span>
      <span className="min-w-0 flex-1">
        <span className="text-foreground line-clamp-2 text-sm font-medium break-all">
          {file.filename}
        </span>
        <span className="text-muted-foreground mt-1 flex items-center gap-2 text-xs">
          <span>{formatBytes(file.size)}</span>
          <span>{formatModifiedTime(file.modified)}</span>
        </span>
      </span>
    </button>
  );
}

export function WorkspaceFilesPanel({
  threadId,
  className,
}: {
  threadId: string;
  className?: string;
}) {
  const [query, setQuery] = useState("");
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const {
    deselect,
    open: artifactsOpen,
    select: selectArtifact,
    selectedArtifact,
    setArtifacts,
    setOpen: setArtifactsOpen,
  } = useArtifacts();

  const threadQuery = useQuery({
    queryKey: ["threads", "detail", threadId],
    queryFn: () => getThread(threadId),
    enabled: Boolean(threadId) && threadId !== "new",
  });

  const workspaceId = threadQuery.data?.workspace_id;

  const filesQuery = useQuery({
    queryKey: ["uploads", "list", workspaceId, threadId],
    queryFn: () => listUploadedFiles(workspaceId!, { threadId }),
    enabled: Boolean(workspaceId),
  });

  useEffect(() => {
    const files = filesQuery.data?.files ?? [];

    if (!artifactsOpen || !selectedArtifact) {
      if (selectedFile !== null) {
        setSelectedFile(null);
      }
      return;
    }

    const selectedWorkspaceFile = files.find(
      (file) => file.virtual_path === selectedArtifact,
    );
    const nextSelectedFile = selectedWorkspaceFile?.object_key ?? null;

    if (nextSelectedFile !== selectedFile) {
      setSelectedFile(nextSelectedFile);
    }
  }, [
    artifactsOpen,
    filesQuery.data?.files,
    selectedArtifact,
    selectedFile,
  ]);

  useEffect(() => {
    if (!selectedFile) {
      return;
    }

    const files = filesQuery.data?.files ?? [];
    if (!files.some((file) => file.object_key === selectedFile)) {
      setSelectedFile(null);
    }
  }, [filesQuery.data?.files, selectedFile]);

  const filteredFiles = useMemo(() => {
    const files = filesQuery.data?.files ?? [];
    const normalizedQuery = query.trim().toLocaleLowerCase();
    if (!normalizedQuery) {
      return files;
    }

    return files.filter((file) =>
      file.filename.toLocaleLowerCase().includes(normalizedQuery),
    );
  }, [filesQuery.data?.files, query]);

  const isLoading =
    threadQuery.isLoading || (Boolean(workspaceId) && filesQuery.isLoading);
  const isRefreshing = threadQuery.isFetching || filesQuery.isFetching;
  const errorMessage =
    threadQuery.error instanceof Error
      ? threadQuery.error.message
      : filesQuery.error instanceof Error
        ? filesQuery.error.message
        : null;

  const handleRefresh = () => {
    setQuery("");
    setSelectedFile(null);
    void filesQuery.refetch();
  };

  const handleFileSelect = (file: UploadedFileInfo) => {
    setSelectedFile(file.object_key);
    setArtifacts((currentArtifacts) => {
      if (currentArtifacts.includes(file.virtual_path)) {
        return currentArtifacts;
      }
      return [...currentArtifacts, file.virtual_path];
    });

    if (!artifactsOpen && selectedArtifact === file.virtual_path) {
      deselect();
      window.setTimeout(() => {
        selectArtifact(file.virtual_path);
        setArtifactsOpen(true);
      }, 0);
      return;
    }

    selectArtifact(file.virtual_path);
    setArtifactsOpen(true);
  };

  return (
    <aside
      className={cn(
        "bg-background/95 border-border/60 flex h-full min-h-0 flex-col border-l backdrop-blur",
        className,
      )}
    >
      <div className="border-border/60 flex shrink-0 flex-col gap-3 border-b px-4 py-4">
        <div className="flex items-start gap-3">
          <div className="min-w-0 flex-1">
            <h2 className="truncate text-sm font-semibold">工作区文件列表</h2>
          </div>
          <Button
            size="icon-sm"
            variant="ghost"
            title="刷新文件列表"
            aria-label="刷新文件列表"
            disabled={isRefreshing}
            onClick={handleRefresh}
          >
            <RefreshCwIcon
              className={cn("size-4", isRefreshing && "animate-spin")}
            />
          </Button>
        </div>
        <InputGroup>
          <InputGroupAddon>
            <SearchIcon className="size-4" />
          </InputGroupAddon>
          <InputGroupInput
            value={query}
            placeholder="搜索文件"
            aria-label="搜索文件"
            onChange={(event) => setQuery(event.target.value)}
          />
        </InputGroup>
      </div>

      <div className="flex min-h-0 flex-1 flex-col px-3 py-4">
        <ScrollArea className="min-h-0 flex-1">
          {isLoading ? (
            <WorkspaceFilesLoading />
          ) : errorMessage ? (
            <WorkspaceFilesEmpty
              title="加载文件失败"
              description={errorMessage}
            />
          ) : !workspaceId ? (
            <WorkspaceFilesEmpty
              title="当前没有工作区"
              description="该会话还没有绑定 workspace_id，暂时无法读取 OSS 文件列表。"
            />
          ) : filteredFiles.length > 0 ? (
            <div className="space-y-2 pr-2">
              {filteredFiles.map((file) => (
                <WorkspaceFileRow
                  key={file.object_key}
                  file={file}
                  selected={selectedFile === file.object_key}
                  onSelect={handleFileSelect}
                />
              ))}
            </div>
          ) : (
            <WorkspaceFilesEmpty
              title={
                (filesQuery.data?.files.length ?? 0) > 0
                  ? "没有匹配的文件"
                  : "工作区中还没有文件"
              }
              description={
                (filesQuery.data?.files.length ?? 0) > 0
                  ? "试试调整搜索关键词。"
                  : "上传文件后会在这里显示。"
              }
            />
          )}
        </ScrollArea>
      </div>
    </aside>
  );
}

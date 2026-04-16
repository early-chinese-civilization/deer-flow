"use client";

import { useQuery } from "@tanstack/react-query";
import {
  AlertCircleIcon,
  ChevronDownIcon,
  ChevronRightIcon,
  DownloadIcon,
  FolderIcon,
  LoaderIcon,
  RefreshCwIcon,
  SearchIcon,
  Trash2Icon,
} from "lucide-react";
import { useEffect, useMemo, useState, type KeyboardEvent } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  InputGroup,
  InputGroupAddon,
  InputGroupInput,
} from "@/components/ui/input-group";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { urlOfArtifact } from "@/core/artifacts/utils";
import { useI18n } from "@/core/i18n/hooks";
import { getThread } from "@/core/threads/api";
import {
  listUploadedFiles,
  type FileTreeNode,
  type UploadedFileInfo,
  useDeleteUploadedFile,
} from "@/core/uploads";
import { removeDeletedVirtualPath } from "@/core/uploads/cache";
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

function WorkspaceDirectoryNode({
  node,
  selectedFile,
  deletingObjectKey,
  downloadLabel,
  deleteLabel,
  onFileSelect,
  onFileDelete,
  threadId,
}: {
  node: FileTreeNode;
  selectedFile: string | null;
  deletingObjectKey: string | undefined;
  downloadLabel: string;
  deleteLabel: string;
  onFileSelect: (file: UploadedFileInfo) => void;
  onFileDelete: (file: UploadedFileInfo) => void;
  threadId: string;
}) {
  const [isExpanded, setIsExpanded] = useState(true);

  return (
    <div className="space-y-1">
      <button
        type="button"
        className="hover:bg-accent/50 flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left transition-colors"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        {isExpanded ? (
          <ChevronDownIcon className="text-muted-foreground size-4 shrink-0" />
        ) : (
          <ChevronRightIcon className="text-muted-foreground size-4 shrink-0" />
        )}
        <FolderIcon className="text-muted-foreground size-4 shrink-0" />
        <span className="text-foreground text-sm font-medium">{node.name}</span>
      </button>
      {isExpanded && node.children && (
        <div className="ml-4 space-y-1">
          {node.children.map((child) =>
            child.type === "directory" ? (
              <WorkspaceDirectoryNode
                key={child.path}
                node={child}
                selectedFile={selectedFile}
                deletingObjectKey={deletingObjectKey}
                downloadLabel={downloadLabel}
                deleteLabel={deleteLabel}
                onFileSelect={onFileSelect}
                onFileDelete={onFileDelete}
                threadId={threadId}
              />
            ) : (
              <WorkspaceFileRow
                key={child.object_key}
                file={{
                  filename: child.filename!,
                  size: child.size!,
                  path: child.path,
                  virtual_path: child.virtual_path!,
                  artifact_url: child.artifact_url!,
                  object_key: child.object_key!,
                  signed_url: child.signed_url,
                  extension: child.extension,
                  modified: child.modified,
                  markdown_file: child.markdown_file,
                  markdown_path: child.markdown_path,
                  markdown_virtual_path: child.markdown_virtual_path,
                  markdown_artifact_url: child.markdown_artifact_url,
                  markdown_object_key: child.markdown_object_key,
                  markdown_signed_url: child.markdown_signed_url,
                }}
                deleting={deletingObjectKey === child.object_key}
                downloadHref={
                  child.artifact_url
                    ? `${child.artifact_url}${child.artifact_url.includes("?") ? "&" : "?"}download=true`
                    : urlOfArtifact({
                        filepath: child.virtual_path!,
                        threadId,
                        download: true,
                      })
                }
                downloadLabel={downloadLabel}
                deleteLabel={deleteLabel}
                selected={selectedFile === child.object_key}
                onSelect={onFileSelect}
                onDelete={onFileDelete}
              />
            ),
          )}
        </div>
      )}
    </div>
  );
}

function WorkspaceFileRow({
  file,
  deleting,
  downloadHref,
  downloadLabel,
  deleteLabel,
  selected,
  onDelete,
  onSelect,
}: {
  file: UploadedFileInfo;
  deleting: boolean;
  downloadHref: string;
  downloadLabel: string;
  deleteLabel: string;
  selected: boolean;
  onDelete: (file: UploadedFileInfo) => void;
  onSelect: (file: UploadedFileInfo) => void;
}) {
  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== "Enter" && event.key !== " ") {
      return;
    }

    event.preventDefault();
    onSelect(file);
  };

  return (
    <div
      role="button"
      tabIndex={0}
      className={cn(
        "border-border/50 hover:bg-accent/70 focus-visible:ring-ring/50 flex w-full items-start gap-3 rounded-lg border px-3 py-3 text-left transition-colors focus-visible:ring-[3px] focus-visible:outline-none",
        selected && "bg-accent border-border",
      )}
      onClick={() => onSelect(file)}
      onKeyDown={handleKeyDown}
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
      <div className="flex shrink-0 items-center gap-1">
        <Button asChild size="icon-sm" variant="ghost">
          <a
            href={downloadHref}
            target="_blank"
            rel="noopener noreferrer"
            title={downloadLabel}
            aria-label={downloadLabel}
            onClick={(event) => {
              event.stopPropagation();
            }}
          >
            <DownloadIcon className="size-4" />
          </a>
        </Button>
        <Button
          size="icon-sm"
          variant="ghost"
          className="text-destructive hover:text-destructive"
          title={deleteLabel}
          aria-label={deleteLabel}
          disabled={deleting}
          onClick={(event) => {
            event.stopPropagation();
            onDelete(file);
          }}
        >
          {deleting ? (
            <LoaderIcon className="size-4 animate-spin" />
          ) : (
            <Trash2Icon className="size-4" />
          )}
        </Button>
      </div>
    </div>
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
  const { t } = useI18n();
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
  const deleteUploadedFile = useDeleteUploadedFile(workspaceId ?? "", {
    threadId,
  });

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

  const filteredTree = useMemo(() => {
    const tree = filesQuery.data?.tree ?? [];
    const normalizedQuery = query.trim().toLocaleLowerCase();

    if (!normalizedQuery) {
      return tree;
    }

    // Filter tree to only show directories and files that match the search
    const filterNode = (node: FileTreeNode): FileTreeNode | null => {
      if (node.type === "file") {
        // Check if file matches search
        if (node.filename?.toLocaleLowerCase().includes(normalizedQuery)) {
          return node;
        }
        return null;
      }

      // For directories, recursively filter children
      if (node.children) {
        const filteredChildren = node.children
          .map(filterNode)
          .filter((child): child is FileTreeNode => child !== null);

        if (filteredChildren.length > 0) {
          return {
            ...node,
            children: filteredChildren,
          };
        }
      }

      return null;
    };

    return tree
      .map(filterNode)
      .filter((node): node is FileTreeNode => node !== null);
  }, [filesQuery.data?.tree, query]);

  const isLoading =
    threadQuery.isLoading || (Boolean(workspaceId) && filesQuery.isLoading);
  const isRefreshing = threadQuery.isFetching || filesQuery.isFetching;
  const errorMessage =
    threadQuery.error instanceof Error
      ? threadQuery.error.message
      : filesQuery.error instanceof Error
        ? filesQuery.error.message
        : null;

  const deletingObjectKey = deleteUploadedFile.variables?.object_key;

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

  const handleFileDelete = async (file: UploadedFileInfo) => {
    if (!workspaceId) {
      return;
    }

    try {
      await deleteUploadedFile.mutateAsync(file);

      if (selectedFile === file.object_key) {
        setSelectedFile(null);
      }

      setArtifacts((currentArtifacts) =>
        removeDeletedVirtualPath(currentArtifacts, file),
      );

      if (
        selectedArtifact &&
        removeDeletedVirtualPath([selectedArtifact], file).length === 0
      ) {
        deselect();
      }

      toast.success(t.uploads.deleteSuccess);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : t.uploads.deleteFailed);
    }
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
            <h2 className="truncate text-sm font-semibold">{t.workspaceFiles.title}</h2>
          </div>
          <Button
            size="icon-sm"
            variant="ghost"
            title={t.workspaceFiles.refresh}
            aria-label={t.workspaceFiles.refresh}
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
            placeholder={t.workspaceFiles.searchPlaceholder}
            aria-label={t.workspaceFiles.searchPlaceholder}
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
              title={t.workspaceFiles.loadFailed}
              description={errorMessage}
            />
          ) : !workspaceId ? (
            <WorkspaceFilesEmpty
              title={t.workspaceFiles.noWorkspace}
              description={t.workspaceFiles.noWorkspaceDescription}
            />
          ) : filteredTree.length > 0 ? (
            <div className="space-y-2 pr-2">
              {filteredTree.map((node) =>
                node.type === "directory" ? (
                  <WorkspaceDirectoryNode
                    key={node.path}
                    node={node}
                    selectedFile={selectedFile}
                    deletingObjectKey={deletingObjectKey}
                    downloadLabel={t.common.download}
                    deleteLabel={t.common.delete}
                    onFileSelect={handleFileSelect}
                    onFileDelete={handleFileDelete}
                    threadId={threadId}
                  />
                ) : (
                  <WorkspaceFileRow
                    key={node.object_key}
                    file={{
                      filename: node.filename!,
                      size: node.size!,
                      path: node.path,
                      virtual_path: node.virtual_path!,
                      artifact_url: node.artifact_url!,
                      object_key: node.object_key!,
                      signed_url: node.signed_url,
                      extension: node.extension,
                      modified: node.modified,
                      markdown_file: node.markdown_file,
                      markdown_path: node.markdown_path,
                      markdown_virtual_path: node.markdown_virtual_path,
                      markdown_artifact_url: node.markdown_artifact_url,
                      markdown_object_key: node.markdown_object_key,
                      markdown_signed_url: node.markdown_signed_url,
                    }}
                    deleting={deletingObjectKey === node.object_key}
                    downloadHref={
                      node.artifact_url
                        ? `${node.artifact_url}${node.artifact_url.includes("?") ? "&" : "?"}download=true`
                        : urlOfArtifact({
                            filepath: node.virtual_path!,
                            threadId,
                            download: true,
                          })
                    }
                    downloadLabel={t.common.download}
                    deleteLabel={t.common.delete}
                    selected={selectedFile === node.object_key}
                    onSelect={handleFileSelect}
                    onDelete={handleFileDelete}
                  />
                ),
              )}
            </div>
          ) : (
            <WorkspaceFilesEmpty
              title={
                (filesQuery.data?.files.length ?? 0) > 0
                  ? t.workspaceFiles.noMatches
                  : t.workspaceFiles.noFiles
              }
              description={
                (filesQuery.data?.files.length ?? 0) > 0
                  ? t.workspaceFiles.noMatchesDescription
                  : t.workspaceFiles.noFilesDescription
              }
            />
          )}
        </ScrollArea>
      </div>
    </aside>
  );
}

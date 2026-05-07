"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircleIcon,
  ChevronDownIcon,
  ChevronRightIcon,
  DownloadIcon,
  FolderIcon,
  RefreshCwIcon,
  SearchIcon,
  XIcon,
} from "lucide-react";
import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  InputGroup,
  InputGroupAddon,
  InputGroupInput,
} from "@/components/ui/input-group";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { useI18n } from "@/core/i18n/hooks";
import { extractPresentFilesFromMessage } from "@/core/messages/utils";
import {
  getBrowserOssSource,
  useResolvedOssUrl,
} from "@/core/oss";
import type { ThreadRecord } from "@/core/threads";
import { getThread } from "@/core/threads/api";
import {
  downloadUploadedFile,
  listUploadedFiles,
  type FileTreeNode,
  type ListFilesResponse,
  type UploadedFileInfo,
} from "@/core/uploads";
import { addObservedWorkspaceFilesToList } from "@/core/uploads/cache";
import { getFileIcon } from "@/core/utils/files";
import { cn } from "@/lib/utils";

import { useArtifacts } from "./artifacts/context";
import { useThread } from "./messages/context";

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
  downloadLabel,
  onFileSelect,
}: {
  node: FileTreeNode;
  selectedFile: string | null;
  downloadLabel: string;
  onFileSelect: (file: UploadedFileInfo) => void;
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
                downloadLabel={downloadLabel}
                onFileSelect={onFileSelect}
              />
            ) : (
              <WorkspaceFileRow
                key={child.object_key}
                file={child as unknown as UploadedFileInfo}
                downloadLabel={downloadLabel}
                selected={selectedFile === child.object_key}
                onSelect={onFileSelect}
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
  downloadLabel,
  selected,
  onSelect,
}: {
  file: UploadedFileInfo;
  downloadLabel: string;
  selected: boolean;
  onSelect: (file: UploadedFileInfo) => void;
}) {
  const { workspaceId } = useThread();
  const source = useMemo(() => getBrowserOssSource(file), [file]);
  const urlResult = useResolvedOssUrl(workspaceId, source);

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== "Enter" && event.key !== " ") {
      return;
    }

    event.preventDefault();
    onSelect(file);
  };

  const handleDownload = () => {
    const url = urlResult.data;
    if (!url) {
      toast.error("Download URL not ready");
      return;
    }
    downloadUploadedFile(url, file.filename).catch((error) => {
      toast.error(
        error instanceof Error ? error.message : "Failed to download file",
      );
    });
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
        <Button
          type="button"
          size="icon-sm"
          variant="ghost"
          title={downloadLabel}
          aria-label={downloadLabel}
          onClick={(event) => {
            event.stopPropagation();
            handleDownload();
          }}
        >
          <span aria-hidden="true">
            <DownloadIcon className="size-4" />
          </span>
        </Button>
      </div>
    </div>
  );
}

export function WorkspaceFilesPanel({
  threadId,
  className,
  onClose,
}: {
  threadId: string;
  className?: string;
  onClose?: () => void;
}) {
  const [query, setQuery] = useState("");
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const { t } = useI18n();
  const { thread, workspaceId } = useThread();
  const queryClient = useQueryClient();
  const {
    artifacts,
    deselect,
    open: artifactsOpen,
    select: selectArtifact,
    selectedArtifact,
    setArtifactSourcesForThread,
    setArtifacts,
    setOpen: setArtifactsOpen,
  } = useArtifacts();
  const processedPresentFilesMessageIdsRef = useRef<Set<string>>(new Set());
  const processedArtifactPathsRef = useRef<Set<string>>(new Set());
  const latestArtifactsRef = useRef(artifacts);
  const latestThreadMessagesRef = useRef(thread.messages);
  const initialThread = useMemo<ThreadRecord | undefined>(
    () =>
      threadId && threadId !== "new"
        ? queryClient.getQueryData<ThreadRecord>([
            "threads",
            "detail",
            threadId,
          ])
        : undefined,
    [queryClient, threadId],
  );

  const threadQuery = useQuery({
    queryKey: ["threads", "detail", threadId],
    queryFn: () => getThread(threadId),
    enabled: !initialThread && Boolean(threadId) && threadId !== "new",
    initialData: initialThread,
    refetchOnWindowFocus: false,
  });

  const filesQuery = useQuery({
    queryKey: ["uploads", "list", workspaceId],
    queryFn: () => listUploadedFiles(workspaceId!),
    enabled: Boolean(workspaceId),
    refetchOnWindowFocus: false,
  });

  const workspaceArtifactSources = useMemo(() => {
    const files = filesQuery.data?.files ?? [];
    return files
      .map((file) => ({
        filepath: file.virtual_path,
        browserOssSource: getBrowserOssSource(file),
      }));
  }, [filesQuery.data?.files]);

  useEffect(() => {
    setArtifactSourcesForThread(threadId, workspaceArtifactSources);
  }, [setArtifactSourcesForThread, threadId, workspaceArtifactSources]);

  useEffect(() => {
    latestArtifactsRef.current = artifacts;
  }, [artifacts]);

  useEffect(() => {
    latestThreadMessagesRef.current = thread.messages;
  }, [thread.messages]);

  useEffect(() => {
    processedPresentFilesMessageIdsRef.current = new Set(
      latestThreadMessagesRef.current
        .filter((message) => extractPresentFilesFromMessage(message).length > 0)
        .map((message) => message.id)
        .filter((messageId): messageId is string => Boolean(messageId)),
    );
    processedArtifactPathsRef.current = new Set(Object.keys(latestArtifactsRef.current));
  }, [threadId]);

  useEffect(() => {
    if (!workspaceId || !filesQuery.data) {
      return;
    }

    const nextVirtualPaths = new Set<string>();

    for (const message of thread.messages) {
      const presentFiles = extractPresentFilesFromMessage(message);
      if (presentFiles.length === 0) {
        continue;
      }

      if (
        message.id &&
        processedPresentFilesMessageIdsRef.current.has(message.id)
      ) {
        continue;
      }

      if (message.id) {
        processedPresentFilesMessageIdsRef.current.add(message.id);
      }

      for (const path of presentFiles) {
        nextVirtualPaths.add(path);
      }
    }

    for (const artifactPath of Object.keys(artifacts)) {
      if (processedArtifactPathsRef.current.has(artifactPath)) {
        continue;
      }

      processedArtifactPathsRef.current.add(artifactPath);
      nextVirtualPaths.add(artifactPath);
    }

    if (nextVirtualPaths.size === 0) {
      return;
    }

    queryClient.setQueriesData<ListFilesResponse | undefined>(
      { queryKey: ["uploads", "list", workspaceId] },
      (current) =>
        addObservedWorkspaceFilesToList(current, Array.from(nextVirtualPaths)),
    );
  }, [artifacts, filesQuery.data, queryClient, thread.messages, workspaceId]);

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
  }, [artifactsOpen, filesQuery.data?.files, selectedArtifact, selectedFile]);

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

  const handleRefresh = () => {
    setQuery("");
    setSelectedFile(null);
    void filesQuery.refetch();
  };

  const handleFileSelect = (file: UploadedFileInfo) => {
    setSelectedFile(file.object_key);
    const ossUri = file.oss_uri ?? file.virtual_path;
    setArtifacts((currentArtifacts) => {
      if (currentArtifacts[file.virtual_path] === ossUri) {
        return currentArtifacts;
      }
      return {
        ...currentArtifacts,
        [file.virtual_path]: ossUri,
      };
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
            <h2 className="truncate text-sm font-semibold">
              {t.workspaceFiles.title}
            </h2>
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
          {onClose && (
            <Button
              size="icon-sm"
              variant="ghost"
              title={t.common.close}
              aria-label={t.common.close}
              onClick={onClose}
            >
              <XIcon className="size-4" />
            </Button>
          )}
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
                    downloadLabel={t.common.download}
                    onFileSelect={handleFileSelect}
                  />
                ) : (
                  <WorkspaceFileRow
                    key={node.object_key}
                    file={node as unknown as UploadedFileInfo}
                    downloadLabel={t.common.download}
                    selected={selectedFile === node.object_key}
                    onSelect={handleFileSelect}
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

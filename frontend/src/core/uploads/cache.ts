import type { FileTreeNode, ListFilesResponse, UploadedFileInfo } from "./api";
import { withBasePathForSameOriginUrl } from "../auth/base-path";

function getDeletedObjectKeys(file: UploadedFileInfo) {
  return new Set<string>([file.object_key]);
}

function getDeletedVirtualPaths(file: UploadedFileInfo) {
  return new Set<string>([file.virtual_path]);
}

function removeDeletedFilesFromTree(
  tree: FileTreeNode[],
  deletedObjectKeys: Set<string>,
): FileTreeNode[] {
  return tree
    .map((node) => {
      if (node.type === "directory") {
        const filteredChildren = node.children
          ? removeDeletedFilesFromTree(node.children, deletedObjectKeys)
          : [];

        if (filteredChildren.length > 0) {
          return {
            ...node,
            children: filteredChildren,
          };
        }
        return null;
      }

      if (node.object_key && deletedObjectKeys.has(node.object_key)) {
        return null;
      }

      return node;
    })
    .filter((node): node is FileTreeNode => node !== null);
}

export function removeDeletedUploadedFilesFromList(
  current: ListFilesResponse | undefined,
  deletedFile: UploadedFileInfo,
) {
  if (!current) {
    return current;
  }

  const deletedObjectKeys = getDeletedObjectKeys(deletedFile);

  const files = current.files.filter(
    (file) => !deletedObjectKeys.has(file.object_key),
  );

  const tree = removeDeletedFilesFromTree(current.tree, deletedObjectKeys);

  return {
    ...current,
    count: files.length,
    files,
    tree,
  };
}

export function removeDeletedVirtualPath(
  currentPaths: string[],
  deletedFile: UploadedFileInfo,
) {
  const deletedVirtualPaths = getDeletedVirtualPaths(deletedFile);

  return currentPaths.filter((path) => !deletedVirtualPaths.has(path));
}

function getRelativePathParts(relativePath: string): string[] {
  const normalizedPath = relativePath.replace(/^\/+|\/+$/g, "");
  if (!normalizedPath) {
    return [];
  }
  return normalizedPath.split("/");
}

function normalizeRelativePathKey(relativePath: string): string {
  return relativePath.replace(/^\/+|\/+$/g, "").toLowerCase();
}

function mergeFilesByRelativePath(
  currentFiles: UploadedFileInfo[],
  nextFiles: UploadedFileInfo[],
  options?: { overwriteExisting?: boolean },
) {
  const overwriteExisting = options?.overwriteExisting ?? true;
  const filesByRelativePath = new Map(
    currentFiles.map((file) => [
      normalizeRelativePathKey(file.relative_path),
      file,
    ] as const),
  );

  for (const file of nextFiles) {
    const relativePathKey = normalizeRelativePathKey(file.relative_path);
    if (!relativePathKey) {
      continue;
    }

    if (!filesByRelativePath.has(relativePathKey) || overwriteExisting) {
      filesByRelativePath.set(relativePathKey, file);
    }
  }

  return Array.from(filesByRelativePath.values());
}

function relativePathFromVirtualPath(virtualPath: string): string | null {
  const normalized = virtualPath.trim();
  if (!normalized) {
    return null;
  }

  const pathMappings = [
    {
      prefix: "/mnt/user-data/uploads/",
      relativePrefix: "uploads/",
    },
    {
      prefix: "/mnt/user-data/outputs/",
      relativePrefix: "outputs/",
    },
    {
      prefix: "/mnt/user-data/workspace/",
      relativePrefix: "workspace/",
    },
  ];

  for (const mapping of pathMappings) {
    if (normalized.startsWith(mapping.prefix)) {
      const suffix = normalized.slice(mapping.prefix.length);
      if (!suffix) {
        return null;
      }
      return `${mapping.relativePrefix}${suffix}`;
    }
  }

  return null;
}

function buildObservedWorkspaceFile(
  virtualPath: string,
): UploadedFileInfo | null {
  const relativePath = relativePathFromVirtualPath(virtualPath);
  if (!relativePath) {
    return null;
  }

  const pathParts = getRelativePathParts(relativePath);
  const filename = pathParts.at(-1);
  if (!filename) {
    return null;
  }

  const extensionIndex = filename.lastIndexOf(".");

  return {
    filename,
    size: 0,
    path: virtualPath,
    virtual_path: virtualPath,
    relative_path: relativePath,
    artifact_url: null,
    http_uri: null,
    oss_uri: null,
    object_key: `virtual:${relativePath}`,
    signed_url: null,
    extension: extensionIndex >= 0 ? filename.slice(extensionIndex) : null,
    markdown_oss_uri: null,
    markdown_http_uri: null,
  };
}

function normalizeWorkspaceFileUrl(url: string | null | undefined) {
  if (!url) {
    return url;
  }

  return withBasePathForSameOriginUrl(url);
}

function normalizeUploadedFile(file: UploadedFileInfo): UploadedFileInfo {
  return {
    ...file,
    artifact_url: normalizeWorkspaceFileUrl(file.artifact_url),
    http_uri: normalizeWorkspaceFileUrl(file.http_uri),
    markdown_artifact_url: normalizeWorkspaceFileUrl(file.markdown_artifact_url),
    markdown_http_uri: normalizeWorkspaceFileUrl(file.markdown_http_uri),
  };
}

function buildFileTree(files: UploadedFileInfo[]): FileTreeNode[] {
  const rootNodes: FileTreeNode[] = [];
  const directoryNodes = new Map<string, FileTreeNode>();

  function ensureDirectory(pathParts: string[]): FileTreeNode {
    const pathKey = pathParts.join("/");
    const existing = directoryNodes.get(pathKey);
    if (existing) {
      return existing;
    }
    const directoryName = pathParts.at(-1);
    if (!directoryName) {
      throw new Error("Directory path parts cannot be empty");
    }

    const dirNode: FileTreeNode = {
      type: "directory",
      name: directoryName,
      path: pathKey,
      children: [],
    };
    directoryNodes.set(pathKey, dirNode);

    if (pathParts.length === 1) {
      rootNodes.push(dirNode);
    } else {
      const parentNode = ensureDirectory(pathParts.slice(0, -1));
      parentNode.children ??= [];
      parentNode.children.push(dirNode);
    }

    return dirNode;
  }

  function sortNodes(nodes: FileTreeNode[]): void {
    nodes.sort((a, b) => {
      // Directories first
      if (a.type !== b.type) {
        return a.type === "directory" ? -1 : 1;
      }
      // Then alphabetically by name (case-insensitive)
      return a.name.toLowerCase().localeCompare(b.name.toLowerCase());
    });

    // Recursively sort children
    for (const node of nodes) {
      if (node.type === "directory" && node.children) {
        sortNodes(node.children);
      }
    }
  }

  for (const file of files) {
    const pathParts = getRelativePathParts(file.relative_path);
    if (pathParts.length === 0) {
      continue;
    }

    const fileNode: FileTreeNode = {
      type: "file",
      name: file.filename,
      path: file.relative_path,
      size: file.size,
      modified: file.modified,
      filename: file.filename,
      virtual_path: file.virtual_path,
      artifact_url: file.artifact_url,
      http_uri: file.http_uri,
      oss_uri: file.oss_uri,
      object_key: file.object_key,
      signed_url: file.signed_url,
      extension: file.extension,
      markdown_file: file.markdown_file,
      markdown_path: file.markdown_path,
      markdown_virtual_path: file.markdown_virtual_path,
      markdown_artifact_url: file.markdown_artifact_url,
      markdown_http_uri: file.markdown_http_uri,
      markdown_oss_uri: file.markdown_oss_uri,
      markdown_object_key: file.markdown_object_key,
      markdown_signed_url: file.markdown_signed_url,
    };

    if (pathParts.length === 1) {
      rootNodes.push(fileNode);
    } else {
      const parentNode = ensureDirectory(pathParts.slice(0, -1));
      parentNode.children ??= [];
      parentNode.children.push(fileNode);
    }
  }

  sortNodes(rootNodes);
  return rootNodes;
}

export function normalizeUploadedFilesList(
  response: ListFilesResponse,
): ListFilesResponse {
  const files = response.files.map(normalizeUploadedFile);

  return {
    ...response,
    files,
    tree: buildFileTree(files),
    count: files.length,
  };
}

/**
 * Add uploaded files to the existing list
 * Uses optimistic update before background reconcile
 */
export function addUploadedFilesToList(
  current: ListFilesResponse | undefined,
  uploadedFiles: UploadedFileInfo[],
): ListFilesResponse | undefined {
  if (!current) {
    return current;
  }

  const updatedFiles = mergeFilesByRelativePath(
    current.files.map(normalizeUploadedFile),
    uploadedFiles.map(normalizeUploadedFile),
    {
      overwriteExisting: true,
    },
  );
  const updatedTree = buildFileTree(updatedFiles);

  return {
    ...current,
    files: updatedFiles,
    tree: updatedTree,
    count: updatedFiles.length,
  };
}

export function addObservedWorkspaceFilesToList(
  current: ListFilesResponse | undefined,
  virtualPaths: string[],
): ListFilesResponse | undefined {
  if (!current || virtualPaths.length === 0) {
    return current;
  }

  const observedFiles = virtualPaths
    .map(buildObservedWorkspaceFile)
    .filter((file): file is UploadedFileInfo => file !== null);

  if (observedFiles.length === 0) {
    return current;
  }

  const updatedFiles = mergeFilesByRelativePath(
    current.files.map(normalizeUploadedFile),
    observedFiles,
    {
      overwriteExisting: false,
    },
  );
  const updatedTree = buildFileTree(updatedFiles);

  return {
    ...current,
    files: updatedFiles,
    tree: updatedTree,
    count: updatedFiles.length,
  };
}

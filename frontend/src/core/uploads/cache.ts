import type { FileTreeNode, ListFilesResponse, UploadedFileInfo } from "./api";

function getDeletedObjectKeys(file: UploadedFileInfo) {
  const objectKeys = new Set<string>([file.object_key]);
  if (file.markdown_object_key) {
    objectKeys.add(file.markdown_object_key);
  }
  return objectKeys;
}

function getDeletedVirtualPaths(file: UploadedFileInfo) {
  const virtualPaths = new Set<string>([file.virtual_path]);
  if (file.markdown_virtual_path) {
    virtualPaths.add(file.markdown_virtual_path);
  }
  return virtualPaths;
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
      object_key: file.object_key,
      signed_url: file.signed_url,
      extension: file.extension,
      markdown_file: file.markdown_file,
      markdown_path: file.markdown_path,
      markdown_virtual_path: file.markdown_virtual_path,
      markdown_artifact_url: file.markdown_artifact_url,
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

  const filesByObjectKey = new Map(
    current.files.map((file) => [file.object_key, file] as const),
  );
  for (const file of uploadedFiles) {
    filesByObjectKey.set(file.object_key, file);
  }
  const updatedFiles = Array.from(filesByObjectKey.values());
  const updatedTree = buildFileTree(updatedFiles);

  return {
    ...current,
    files: updatedFiles,
    tree: updatedTree,
    count: updatedFiles.length,
  };
}

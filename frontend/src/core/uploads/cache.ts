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

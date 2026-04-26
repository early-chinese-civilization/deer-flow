import { getWorkspaceDownloadUrl } from "../uploads/api.ts";

export { type WorkspaceDownloadUrlResponse } from "../uploads/api.ts";

export function resolveWorkspaceDownloadUrl(
  workspaceId: string,
  objectKey: string,
) {
  return getWorkspaceDownloadUrl(workspaceId, objectKey);
}

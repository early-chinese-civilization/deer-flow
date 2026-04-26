import type { BrowserOssSource } from "./source.ts";

export function getResolvedOssUrlQueryKey(
  workspaceId: string | null | undefined,
  source: BrowserOssSource | null,
) {
  return ["oss", "download-url", workspaceId, source?.objectKey] as const;
}

export function isResolvedOssUrlQueryEnabled(
  workspaceId: string | null | undefined,
  source: BrowserOssSource | null,
) {
  return Boolean(workspaceId && source);
}

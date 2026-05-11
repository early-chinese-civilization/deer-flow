import { useQuery } from "@tanstack/react-query";

import { resolveWorkspaceDownloadUrl } from "./api";
import {
  getResolvedOssUrlQueryKey,
  isResolvedOssUrlQueryEnabled,
} from "./query";
import type { BrowserOssSource } from "./source";

export function useResolvedOssUrl(
  workspaceId: string | null | undefined,
  source: BrowserOssSource | null,
) {
  return useQuery({
    queryKey: getResolvedOssUrlQueryKey(workspaceId, source),
    enabled: isResolvedOssUrlQueryEnabled(workspaceId, source),
    queryFn: async () => {
      if (!source || !workspaceId) {
        throw new Error("OSS source and workspace id are required.");
      }
      if (source?.httpUri) {
        return source.httpUri;
      }

      const result = await resolveWorkspaceDownloadUrl(
        workspaceId,
        source.objectKey,
      );

      return result.download_url;
    },
  });
}

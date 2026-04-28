import { useQuery } from "@tanstack/react-query";

import { resolveWorkspaceDownloadUrl } from "./api";
import type { BrowserOssSource } from "./source";
import {
  getResolvedOssUrlQueryKey,
  isResolvedOssUrlQueryEnabled,
} from "./query";

export function useResolvedOssUrl(
  workspaceId: string | null | undefined,
  source: BrowserOssSource | null,
) {
  return useQuery({
    queryKey: getResolvedOssUrlQueryKey(workspaceId, source),
    enabled: isResolvedOssUrlQueryEnabled(workspaceId, source),
    queryFn: async () => {
      if (source?.httpUri) {
        return source.httpUri;
      }

      const result = await resolveWorkspaceDownloadUrl(
        workspaceId as string,
        source?.objectKey as string,
      );

      return result.download_url;
    },
  });
}

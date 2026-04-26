import { useQuery } from "@tanstack/react-query";

import { resolveWorkspaceDownloadUrl } from "./api.ts";
import type { BrowserOssSource } from "./source.ts";
import {
  getResolvedOssUrlQueryKey,
  isResolvedOssUrlQueryEnabled,
} from "./query.ts";

export function useResolvedOssUrl(
  workspaceId: string | null | undefined,
  source: BrowserOssSource | null,
) {
  return useQuery({
    queryKey: getResolvedOssUrlQueryKey(workspaceId, source),
    enabled: isResolvedOssUrlQueryEnabled(workspaceId, source),
    queryFn: async () => {
      const result = await resolveWorkspaceDownloadUrl(
        workspaceId as string,
        source?.objectKey as string,
      );

      return result.download_url;
    },
  });
}

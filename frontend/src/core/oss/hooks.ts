import { useQuery } from "@tanstack/react-query";

import { resolveWorkspaceDownloadUrl } from "./api.ts";
import type { BrowserOssSource } from "./source.ts";

export function useResolvedOssUrl(
  workspaceId: string | null | undefined,
  source: BrowserOssSource | null,
) {
  return useQuery({
    queryKey: ["oss", "download-url", workspaceId, source?.ossUri, source?.objectKey],
    enabled: Boolean(workspaceId && source),
    queryFn: async () => {
      const result = await resolveWorkspaceDownloadUrl(
        workspaceId as string,
        source?.objectKey as string,
      );

      return result.download_url;
    },
    staleTime: 5 * 60 * 1000,
  });
}

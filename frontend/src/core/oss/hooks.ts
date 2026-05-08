import { useQuery } from "@tanstack/react-query";

import { withBasePath } from "../config/index.ts";

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
      if (source?.httpUri) {
        return withBasePath(source.httpUri);
      }

      const result = await resolveWorkspaceDownloadUrl(
        workspaceId!,
        source!.objectKey,
      );

      return result.download_url;
    },
  });
}

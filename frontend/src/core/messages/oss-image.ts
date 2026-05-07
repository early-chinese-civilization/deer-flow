import { useMemo } from "react";
import { useQueries } from "@tanstack/react-query";
import { visit } from "unist-util-visit";

function normalizeOssUriCandidate(value: string) {
  let text = value;
  while (text && ",.;:!?)]}*".includes(text[text.length - 1] ?? "")) {
    text = text.slice(0, -1);
  }
  return text;
}

function getBaseOrigin(): string {
  if (typeof window !== "undefined") {
    return window.location.origin;
  }

  return "http://localhost:2026";
}

function getBackendBaseURL(): string {
  const backendBaseURL = process.env.NEXT_PUBLIC_BACKEND_BASE_URL;

  if (backendBaseURL) {
    return new URL(backendBaseURL, getBaseOrigin()).toString().replace(/\/+$/, "");
  }

  return "";
}

function buildDownloadUrlUrl(workspaceId: string, objectKey: string): string {
  const query = new URLSearchParams({ object_key: objectKey }).toString();
  return `${getBackendBaseURL()}/api/workspaces/${encodeURIComponent(workspaceId)}/uploads/download-url?${query}`;
}

async function resolveWorkspaceDownloadUrl(
  workspaceId: string,
  objectKey: string,
): Promise<{ download_url: string; oss_uri: string }> {
  const response = await fetch(buildDownloadUrlUrl(workspaceId, objectKey), {
    credentials: "include",
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Failed to get download URL" }));
    throw new Error(error.detail ?? "Failed to get download URL");
  }

  return response.json();
}

function getObjectKeyFromOssUri(ossUri: string): string | null {
  const normalizedOssUri = normalizeOssUriCandidate(ossUri);

  if (!normalizedOssUri.startsWith("oss://")) {
    return null;
  }

  const withoutScheme = normalizedOssUri.slice("oss://".length);
  const firstSlash = withoutScheme.indexOf("/");
  if (firstSlash < 0) {
    return null;
  }

  const bucket = withoutScheme.slice(0, firstSlash);
  let objectKey: string;
  try {
    objectKey = decodeURIComponent(withoutScheme.slice(firstSlash + 1));
  } catch {
    return null;
  }
  if (!bucket || !objectKey) {
    return null;
  }

  return objectKey;
}

function extractOssUris(content: string): string[] {
  const matches = content.match(/oss:\/\/[^\s<>'"\]]+/g);
  if (!matches) {
    return [];
  }

  return Array.from(
    new Set(
      matches
        .map((match) => normalizeOssUriCandidate(match))
        .filter(Boolean),
    ),
  );
}

export function useResolvedOssUrlMap(
  workspaceId: string | null | undefined,
  content: string,
) {
  const ossUris = useMemo(() => extractOssUris(content), [content]);
  const queries = useQueries({
    queries: ossUris.map((ossUri) => {
      const objectKey = getObjectKeyFromOssUri(ossUri);
      return {
        queryKey: ["oss", "download-url", workspaceId, objectKey] as const,
        enabled: Boolean(workspaceId && objectKey),
        queryFn: async () => {
          const result = await resolveWorkspaceDownloadUrl(
            workspaceId as string,
            objectKey as string,
          );
          return result.download_url;
        },
      };
    }),
  });

  const map: Record<string, string> = {};
  for (let index = 0; index < ossUris.length; index += 1) {
    const ossUri = ossUris[index];
    const url = queries[index]?.data;
    if (ossUri && typeof url === "string") {
      map[ossUri] = url;
    }
  }

  return map;
}

export function remarkRewriteResolvedOssUrls(urlMap: Record<string, string>) {
  return () => {
    return (tree: unknown) => {
      visit(tree as any, ["image", "link"], (node: any) => {
        if (typeof node.url !== "string") {
          return;
        }

    const resolved = urlMap[normalizeOssUriCandidate(node.url)] ?? urlMap[node.url];
        if (resolved) {
          node.url = resolved;
        }
      });
    };
  };
}

export function rewriteMarkdownImageUrls(
  content: string,
  urlMap: Record<string, string>,
) {
    return content.replace(/(!\[[^\]]*\]\()([^\s)]+)(\))/g, (match, prefix, url, suffix) => {
    if (typeof url !== "string") {
      return match;
    }
    const resolved = urlMap[normalizeOssUriCandidate(url)] ?? urlMap[url];
    if (!resolved) {
      return match;
    }
    return `${prefix}${resolved}${suffix}`;
  });
}

export { extractOssUris, getObjectKeyFromOssUri };

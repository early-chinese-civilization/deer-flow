import { withBasePathForSameOriginUrl } from "../auth/base-path";

export interface BrowserOssSource {
  ossUri: string;
  objectKey: string;
  httpUri?: string | null;
}

export interface FileLikeOssSource {
  oss_uri?: string | null;
  object_key?: string | null;
  http_uri?: string | null;
  artifact_url?: string | null;
}

function splitOssUri(ossUri: string): { ossUri: string; objectKey: string } | null {
  if (!ossUri.startsWith("oss://")) {
    return null;
  }

  const withoutScheme = ossUri.slice("oss://".length);
  const firstSlash = withoutScheme.indexOf("/");
  if (firstSlash < 0) {
    return null;
  }

  const bucket = withoutScheme.slice(0, firstSlash);
  const objectKey = decodeURIComponent(withoutScheme.slice(firstSlash + 1));
  if (!bucket || !objectKey) {
    return null;
  }

  return {
    ossUri,
    objectKey,
  };
}

export function getBrowserOssSource(
  file: FileLikeOssSource,
): BrowserOssSource | null {
  if (!file.oss_uri || !file.object_key) {
    return null;
  }

  return {
    ossUri: file.oss_uri,
    objectKey: file.object_key,
    httpUri: normalizeBrowserHttpUri(file.http_uri ?? file.artifact_url ?? null),
  };
}

export function getBrowserOssSourceFromOssUri(
  ossUri: string | null | undefined,
): BrowserOssSource | null {
  if (!ossUri) {
    return null;
  }

  return splitOssUri(ossUri);
}

function normalizeBrowserHttpUri(httpUri: string | null | undefined) {
  if (!httpUri) {
    return null;
  }

  return withBasePathForSameOriginUrl(httpUri);
}

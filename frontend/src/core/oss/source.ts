export interface BrowserOssSource {
  ossUri: string;
  objectKey: string;
}

export interface FileLikeOssSource {
  oss_uri?: string | null;
  object_key?: string | null;
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
  };
}

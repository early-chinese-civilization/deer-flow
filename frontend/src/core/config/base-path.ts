const SCHEME_URL_PATTERN = /^[a-z][a-z\d+\-.]*:/i;

function isRootRelativePath(value: string): boolean {
  return value.startsWith("/") && !value.startsWith("//");
}

function hasBasePath(path: string, basePath: string): boolean {
  return (
    path === basePath ||
    path.startsWith(`${basePath}/`) ||
    path.startsWith(`${basePath}?`) ||
    path.startsWith(`${basePath}#`)
  );
}

export function normalizeBasePath(value: string | null | undefined): string {
  const trimmed = value?.trim();
  if (!trimmed || trimmed === "/") {
    return "";
  }

  const normalized = `/${trimmed.replace(/^\/+|\/+$/g, "")}`;
  return normalized === "/" ? "" : normalized;
}

export function withBasePathFor(
  basePathValue: string | null | undefined,
  path: string,
): string {
  if (SCHEME_URL_PATTERN.test(path) || !isRootRelativePath(path)) {
    return path;
  }

  const basePath = normalizeBasePath(basePathValue);
  if (!basePath || hasBasePath(path, basePath)) {
    return path;
  }

  if (path === "/") {
    return basePath;
  }

  return `${basePath}${path}`;
}

export function withoutBasePathFor(
  basePathValue: string | null | undefined,
  path: string,
): string {
  const basePath = normalizeBasePath(basePathValue);
  if (!basePath || !hasBasePath(path, basePath)) {
    return path;
  }

  if (path === basePath) {
    return "/";
  }

  const nextPath = path.slice(basePath.length);
  return nextPath.startsWith("/") ? nextPath : `/${nextPath}`;
}

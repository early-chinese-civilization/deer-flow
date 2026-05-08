function getBasePath(): string {
  return (
    process.env.NEXT_PUBLIC_BASE_PATH ??
    process.env.DEER_FLOW_PUBLIC_BASE_PATH ??
    ""
  ).replace(/\/+$/, "");
}

export function withBasePath(path: string): string {
  const basePath = getBasePath();
  if (!basePath || path === basePath || path.startsWith(`${basePath}/`)) {
    return path;
  }
  return `${basePath}${path.startsWith("/") ? path : `/${path}`}`;
}

export function withBasePathForSameOriginUrl(url: string): string {
  if (!getBasePath()) {
    return url;
  }

  if (url.startsWith("//")) {
    return url;
  }

  if (url.startsWith("/")) {
    return withBasePath(url);
  }

  if (typeof window === "undefined") {
    return url;
  }

  const parsedUrl = new URL(url, window.location.href);
  if (parsedUrl.origin !== window.location.origin) {
    return url;
  }

  const pathWithBase = withBasePath(
    `${parsedUrl.pathname}${parsedUrl.search}${parsedUrl.hash}`,
  );
  return `${parsedUrl.origin}${pathWithBase}`;
}

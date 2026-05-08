import { env } from "../../env.js";

import {
  normalizeBasePath,
  withBasePathFor,
  withoutBasePathFor,
} from "./base-path.ts";

export { normalizeBasePath, withBasePathFor, withoutBasePathFor };

function getBaseOrigin() {
  if (typeof window !== "undefined") {
    return window.location.origin;
  }
  // Fallback for SSR
  return "http://localhost:2026";
}

export function getBackendBaseURL() {
  if (env.NEXT_PUBLIC_BACKEND_BASE_URL) {
    return new URL(
      withBasePath(env.NEXT_PUBLIC_BACKEND_BASE_URL),
      getBaseOrigin(),
    )
      .toString()
      .replace(/\/+$/, "");
  } else {
    return getBasePath();
  }
}

export function getBasePath() {
  return normalizeBasePath(env.NEXT_PUBLIC_BASE_PATH);
}

export function withBasePath(path: string) {
  return withBasePathFor(getBasePath(), path);
}

export function withoutBasePath(path: string) {
  return withoutBasePathFor(getBasePath(), path);
}

export function getLangGraphBaseURL(isMock?: boolean) {
  if (env.NEXT_PUBLIC_LANGGRAPH_BASE_URL) {
    return new URL(
      withBasePath(env.NEXT_PUBLIC_LANGGRAPH_BASE_URL),
      getBaseOrigin(),
    ).toString();
  } else if (isMock) {
    if (typeof window !== "undefined") {
      return `${window.location.origin}${withBasePath("/mock/api")}`;
    }
    return `http://localhost:3000${withBasePath("/mock/api")}`;
  } else {
    // LangGraph SDK requires a full URL, construct it from current origin
    if (typeof window !== "undefined") {
      return `${window.location.origin}${withBasePath("/api/langgraph")}`;
    }
    // Fallback for SSR
    return `http://localhost:2026${withBasePath("/api/langgraph")}`;
  }
}

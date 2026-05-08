/**
 * 认证 API 客户端
 *
 * 提供与后端认证接口交互的方法
 */

import { withBasePath } from "../config/index.ts";

export interface User {
  id: number;
  externalAuthId: string;
  username: string;
  displayName: string;
  email?: string;
  givenName?: string;
  familyName?: string;
  emailVerified: boolean;
}

export interface MeResponse {
  user: User;
}

export interface LogoutResponse {
  logoutUrl: string;
}

type AuthErrorPayload = {
  detail?: unknown;
};

const EXPECTED_UNAUTHENTICATED_DETAILS = new Set([
  "Not authenticated",
  "Session expired",
  "Logged out",
]);

async function readAuthErrorDetail(response: Response): Promise<string> {
  const body = await response.text();
  if (!body) {
    return response.statusText || "Unknown auth error";
  }

  try {
    const payload = JSON.parse(body) as AuthErrorPayload;
    if (typeof payload.detail === "string") {
      return payload.detail;
    }
    if (payload.detail != null) {
      return JSON.stringify(payload.detail);
    }
  } catch {
    // Fall through to the raw response body below.
  }

  return body;
}

function shouldLogAuthFailure(status: number, detail: string): boolean {
  if (status >= 500) {
    return true;
  }
  return !EXPECTED_UNAUTHENTICATED_DETAILS.has(detail);
}

function formatAuthError(
  action: string,
  status: number,
  detail: string,
): string {
  return `${action} failed (${status}): ${detail}`;
}

/**
 * 获取当前用户信息
 *
 * 如果 session 过期，后端会自动尝试刷新
 */
export async function getCurrentUser(): Promise<User | null> {
  try {
    const res = await fetch(withBasePath("/api/auth/me"), {
      credentials: "include", // 重要：携带 cookie
    });

    if (!res.ok) {
      const detail = await readAuthErrorDetail(res);
      if (shouldLogAuthFailure(res.status, detail)) {
        console.error(
          formatAuthError("Current user lookup", res.status, detail),
        );
      }
      return null;
    }

    const data: MeResponse = await res.json();
    return data.user;
  } catch (error) {
    console.error("Failed to get current user:", error);
    return null;
  }
}

/**
 * 登出
 *
 * 返回 Keycloak 登出 URL，前端需要跳转到该 URL
 */
export async function logout(): Promise<string> {
  try {
    const res = await fetch(withBasePath("/api/auth/logout"), {
      method: "POST",
      credentials: "include",
    });

    if (!res.ok) {
      const detail = await readAuthErrorDetail(res);
      throw new Error(formatAuthError("Logout", res.status, detail));
    }

    const data: LogoutResponse = await res.json();
    return withBasePath(data.logoutUrl);
  } catch (error) {
    console.error("Logout failed:", error);
    // 返回默认登出 URL
    return withBasePath("/");
  }
}

/**
 * 主动刷新 token
 *
 * 通常不需要手动调用，/api/auth/me 会自动刷新
 */
export async function refreshToken(): Promise<boolean> {
  try {
    const res = await fetch(withBasePath("/api/auth/refresh"), {
      method: "POST",
      credentials: "include",
    });

    if (!res.ok) {
      const detail = await readAuthErrorDetail(res);
      if (shouldLogAuthFailure(res.status, detail)) {
        console.error(formatAuthError("Token refresh", res.status, detail));
      }
      return false;
    }

    return true;
  } catch (error) {
    console.error("Token refresh failed:", error);
    return false;
  }
}

/**
 * 发起登录
 *
 * @param returnTo - 登录成功后跳转的路径（默认 /workspace）
 */
export function login(returnTo?: string) {
  const params = new URLSearchParams();
  if (returnTo) {
    params.set("return_to", returnTo);
  }

  const url = withBasePath(
    `/api/auth/login${params.toString() ? "?" + params.toString() : ""}`,
  );
  window.location.href = url;
}

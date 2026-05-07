/**
 * 认证 API 客户端
 *
 * 提供与后端认证接口交互的方法
 */

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

/**
 * 获取当前用户信息
 *
 * 如果 session 过期，后端会自动尝试刷新
 */
export async function getCurrentUser(): Promise<User | null> {
  try {
    const res = await fetch("/api/auth/me", {
      credentials: "include", // 重要：携带 cookie
    });

    if (!res.ok) {
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
    const res = await fetch("/api/auth/logout", {
      method: "POST",
      credentials: "include",
    });

    if (!res.ok) {
      throw new Error("Logout failed");
    }

    const data: LogoutResponse = await res.json();
    return data.logoutUrl;
  } catch (error) {
    console.error("Logout failed:", error);
    // 返回默认登出 URL
    return "/";
  }
}

/**
 * 主动刷新 token
 *
 * 通常不需要手动调用，/api/auth/me 会自动刷新
 */
export async function refreshToken(): Promise<boolean> {
  try {
    const res = await fetch("/api/auth/refresh", {
      method: "POST",
      credentials: "include",
    });

    return res.ok;
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

  const url = `/api/auth/login${params.toString() ? "?" + params.toString() : ""}`;
  window.location.href = url;
}

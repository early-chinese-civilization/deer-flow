import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const TRUE_VALUES = new Set(["1", "true", "yes", "on"]);

function isTruthy(value: string | undefined) {
  return TRUE_VALUES.has((value ?? "").trim().toLowerCase());
}

function isDevSyntheticAuthEnabled() {
  const enabled = isTruthy(process.env.DEER_FLOW_DEV_SYNTHETIC_AUTH);
  const isDevelopment =
    process.env.DEER_FLOW_SERVER_MODE === "dev" ||
    process.env.NODE_ENV === "development";
  return enabled && isDevelopment;
}

/**
 * Next.js Middleware - 路由保护
 *
 * 保护需要登录才能访问的路由
 */
export function middleware(request: NextRequest) {
  if (isDevSyntheticAuthEnabled()) {
    return NextResponse.next();
  }

  const accessTokenCookie = request.cookies.get("kc_access_token");
  const refreshTokenCookie = request.cookies.get("kc_refresh_token");
  const logoutMarkerCookie = request.cookies.get("kc_logout_marker");

  // 保护 /workspace 路由
  if (request.nextUrl.pathname.startsWith("/workspace")) {
    if (logoutMarkerCookie) {
      return NextResponse.redirect(new URL("/signed-out", request.url));
    }

    if (!accessTokenCookie && !refreshTokenCookie) {
      // 未登录，先进入同源登录启动页；由浏览器顶层跳转启动 OIDC。
      const loginUrl = new URL("/auth/login", request.url);
      loginUrl.searchParams.set(
        "return_to",
        `${request.nextUrl.pathname}${request.nextUrl.search}`,
      );
      return NextResponse.redirect(loginUrl);
    }
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/workspace/:path*"],
};

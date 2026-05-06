import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const TRUE_VALUES = new Set(["1", "true", "yes", "on"]);
const DEV_SYNTHETIC_MODES = new Set(["dev", "development", "local", "test"]);
const BASE_PATH = (process.env.NEXT_PUBLIC_BASE_PATH ?? "").replace(/\/+$/, "");

function isTruthy(value: string | undefined) {
  return TRUE_VALUES.has((value ?? "").trim().toLowerCase());
}

function isDevSyntheticAuthEnabled() {
  const enabled = isTruthy(process.env.DEER_FLOW_DEV_SYNTHETIC_AUTH);
  const mode = process.env.DEER_FLOW_SERVER_MODE ?? process.env.NODE_ENV;
  return enabled && DEV_SYNTHETIC_MODES.has((mode ?? "").trim().toLowerCase());
}

function withBasePath(path: string) {
  if (!BASE_PATH || path === BASE_PATH || path.startsWith(`${BASE_PATH}/`)) {
    return path;
  }
  return `${BASE_PATH}${path.startsWith("/") ? path : `/${path}`}`;
}

export function middleware(request: NextRequest) {
  if (isDevSyntheticAuthEnabled()) {
    return NextResponse.next();
  }

  const accessTokenCookie = request.cookies.get("kc_access_token");
  const refreshTokenCookie = request.cookies.get("kc_refresh_token");
  const logoutMarkerCookie = request.cookies.get("kc_logout_marker");

  if (request.nextUrl.pathname.startsWith("/workspace")) {
    if (logoutMarkerCookie) {
      return NextResponse.redirect(
        new URL(withBasePath("/signed-out"), request.url),
      );
    }

    if (!accessTokenCookie && !refreshTokenCookie) {
      const loginUrl = new URL(withBasePath("/auth/login"), request.url);
      loginUrl.searchParams.set(
        "return_to",
        withBasePath(`${request.nextUrl.pathname}${request.nextUrl.search}`),
      );
      return NextResponse.redirect(loginUrl);
    }
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/workspace/:path*"],
};

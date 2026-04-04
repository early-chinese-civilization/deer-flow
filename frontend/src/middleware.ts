import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

/**
 * Next.js Middleware - 路由保护
 *
 * 保护需要登录才能访问的路由
 */
export function middleware(request: NextRequest) {
  const sessionCookie = request.cookies.get('deer_session');

  // 保护 /workspace 路由
  if (request.nextUrl.pathname.startsWith('/workspace')) {
    if (!sessionCookie) {
      // 未登录，重定向到登录页面
      const loginUrl = new URL('/api/auth/login', request.url);
      loginUrl.searchParams.set('returnTo', request.nextUrl.pathname);
      return NextResponse.redirect(loginUrl);
    }
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    '/workspace/:path*',
  ],
};

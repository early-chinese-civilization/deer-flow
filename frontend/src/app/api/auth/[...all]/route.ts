import type { NextRequest } from "next/server";

const GATEWAY_BASE_URL =
  process.env.DEER_FLOW_INTERNAL_GATEWAY_BASE_URL ??
  process.env.NEXT_PUBLIC_BACKEND_BASE_URL ??
  "http://127.0.0.1:8001";

function buildGatewayUrl(pathname: string, search: string) {
  const url = new URL(pathname, GATEWAY_BASE_URL);
  url.search = search;
  return url;
}

async function proxyRequest(
  request: NextRequest,
  pathname: string,
): Promise<Response> {
  const headers = new Headers(request.headers);
  headers.delete("host");
  headers.delete("connection");
  headers.delete("content-length");

  const hasBody = !["GET", "HEAD"].includes(request.method);
  const response = await fetch(
    buildGatewayUrl(pathname, request.nextUrl.search),
    {
      method: request.method,
      headers,
      body: hasBody ? await request.arrayBuffer() : undefined,
      // 认证接口需要把 Gateway 的 302/401 原样回给浏览器，不能让 Next 在服务端吞掉跳转。
      redirect: "manual",
    },
  );

  return new Response(await response.arrayBuffer(), {
    status: response.status,
    headers: response.headers,
  });
}

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ all: string[] }> },
) {
  const { all } = await params;
  return proxyRequest(request, `/api/auth/${all.join("/")}`);
}

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ all: string[] }> },
) {
  const { all } = await params;
  return proxyRequest(request, `/api/auth/${all.join("/")}`);
}

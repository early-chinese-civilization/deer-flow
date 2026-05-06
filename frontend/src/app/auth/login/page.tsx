import { LoginRedirect } from "./login-redirect";

type LoginPageProps = {
  searchParams: Promise<{
    return_to?: string | string[];
  }>;
};

const BASE_PATH = (process.env.NEXT_PUBLIC_BASE_PATH ?? "").replace(/\/+$/, "");

function withBasePath(path: string) {
  if (!BASE_PATH || path === BASE_PATH || path.startsWith(`${BASE_PATH}/`)) {
    return path;
  }
  return `${BASE_PATH}${path.startsWith("/") ? path : `/${path}`}`;
}

function normalizeReturnTo(value: string | string[] | undefined): string {
  const rawValue = Array.isArray(value) ? value[0] : value;
  if (!rawValue || !rawValue.startsWith("/") || rawValue.startsWith("//")) {
    return withBasePath("/workspace");
  }
  return withBasePath(rawValue);
}

export default async function LoginPage({ searchParams }: LoginPageProps) {
  const params = await searchParams;
  return <LoginRedirect returnTo={normalizeReturnTo(params.return_to)} />;
}

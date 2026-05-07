import { withBasePath } from "@/core/auth/base-path";
import { LoginRedirect } from "./login-redirect";

type LoginPageProps = {
  searchParams: Promise<{
    return_to?: string | string[];
  }>;
};

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

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { CallbackErrorPage } from "@/components/auth/callback-error-page";
import { normalizeCallbackError } from "@/core/auth/callback-error";
import { WORKSPACE_HOME_PATH } from "@/core/config/home-path";

type HomePageProps = {
  searchParams: Promise<{
    error?: string | string[];
  }>;
};

export default async function HomePage({ searchParams }: HomePageProps) {
  const cookieStore = await cookies();
  const params = await searchParams;

  if (cookieStore.get("kc_logout_marker")) {
    redirect("/signed-out");
  }

  const authError = normalizeCallbackError(params.error);
  if (authError) {
    return <CallbackErrorPage error={authError} />;
  }

  redirect(WORKSPACE_HOME_PATH);
}

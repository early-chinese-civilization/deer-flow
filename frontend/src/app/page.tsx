import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { WORKSPACE_HOME_PATH } from "@/core/config/home-path";

export default async function HomePage() {
  const cookieStore = await cookies();
  if (cookieStore.get("kc_logout_marker")) {
    redirect("/signed-out");
  }

  redirect(WORKSPACE_HOME_PATH);
}

import { redirect } from "next/navigation";

import { WORKSPACE_HOME_PATH } from "@/core/config/home-path";

export default function HomePage() {
  redirect(WORKSPACE_HOME_PATH);
}

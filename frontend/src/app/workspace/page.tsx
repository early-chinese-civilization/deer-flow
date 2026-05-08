import fs from "fs";
import path from "path";

import { redirect } from "next/navigation";

import { pathOfNewThread, pathOfThread } from "@/core/threads/utils";
import { env } from "@/env";

export default function WorkspacePage() {
  if (env.NEXT_PUBLIC_STATIC_WEBSITE_ONLY === "true") {
    const firstThread = fs
      .readdirSync(path.resolve(process.cwd(), "public/demo/threads"), {
        withFileTypes: true,
      })
      .find((thread) => thread.isDirectory() && !thread.name.startsWith("."));
    if (firstThread) {
      return redirect(pathOfThread(firstThread.name));
    }
  }
  return redirect(pathOfNewThread());
}

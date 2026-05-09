"use client";

import { MessageSquarePlus } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import {
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarTrigger,
  useSidebar,
} from "@/components/ui/sidebar";
import { useI18n } from "@/core/i18n/hooks";
import { pathOfNewThread } from "@/core/threads/utils";
import { uuid } from "@/core/utils/uuid";
import { env } from "@/env";
import { cn } from "@/lib/utils";

export function WorkspaceHeader({ className }: { className?: string }) {
  const { t } = useI18n();
  const { state } = useSidebar();
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();

  function handleNewChat() {
    router.push(
      pathOfNewThread({
        currentSearch: searchParams.toString(),
        agentName: null,
        draftNonce: uuid(),
      }),
    );
  }

  return (
    <>
      <div
        className={cn(
          "group/workspace-header flex h-12 flex-col justify-center",
          className,
        )}
      >
        {state === "collapsed" ? (
          <div className="group-has-data-[collapsible=icon]/sidebar-wrapper:-translate-y flex w-full cursor-pointer items-center justify-center">
            <div
              className="text-primary inline-flex size-8 shrink-0 items-center justify-center rounded-md font-serif text-sm leading-none whitespace-nowrap group-hover/workspace-header:hidden"
              title={t.brand.shortName}
              aria-label={t.brand.shortName}
            >
              {t.brand.mark}
            </div>
            <SidebarTrigger className="hidden pl-2 group-hover/workspace-header:block" />
          </div>
        ) : (
          <div className="flex min-w-0 items-center justify-between gap-2">
            {env.NEXT_PUBLIC_STATIC_WEBSITE_ONLY === "true" ? (
              <Link
                href="/"
                className="text-primary ml-2 min-w-0 flex-1 truncate font-serif"
                title={t.brand.shortName}
              >
                {t.brand.shortName}
              </Link>
            ) : (
              <div
                className="text-primary ml-2 min-w-0 flex-1 truncate font-serif"
                title={t.brand.shortName}
              >
                {t.brand.shortName}
              </div>
            )}
            <SidebarTrigger />
          </div>
        )}
      </div>
      <SidebarMenu>
        <SidebarMenuItem>
          <SidebarMenuButton
            isActive={pathname === "/workspace/chats/new"}
            onClick={handleNewChat}
          >
            <MessageSquarePlus size={16} />
            <span>{t.sidebar.newChat}</span>
          </SidebarMenuButton>
        </SidebarMenuItem>
      </SidebarMenu>
    </>
  );
}

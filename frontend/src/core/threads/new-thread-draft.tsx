"use client";

import { usePathname, useRouter } from "next/navigation";
import {
  createContext,
  type PropsWithChildren,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { uuid } from "@/core/utils/uuid";

import {
  getLegacyDraftQueryValue,
  isNewThreadPathname,
  shouldResetNewThreadDraftKey,
} from "./new-thread-draft-core";
import { pathOfNewThread } from "./utils";

type NewThreadDraftContextValue = {
  draftKey: string;
};

const NewThreadDraftContext = createContext<NewThreadDraftContextValue | null>(
  null,
);

function createInitialDraftKey() {
  if (typeof window === "undefined") {
    return uuid();
  }

  return getLegacyDraftQueryValue(window.location.search) ?? uuid();
}

export function NewThreadDraftProvider({ children }: PropsWithChildren) {
  const pathname = usePathname();
  const previousPathnameRef = useRef<string | null>(null);
  const [draftKey, setDraftKey] = useState(createInitialDraftKey);

  useEffect(() => {
    if (shouldResetNewThreadDraftKey(previousPathnameRef.current, pathname)) {
      setDraftKey(uuid());
    }
    previousPathnameRef.current = pathname;
  }, [pathname]);

  const value = useMemo(() => ({ draftKey }), [draftKey]);

  return (
    <NewThreadDraftContext.Provider value={value}>
      {children}
    </NewThreadDraftContext.Provider>
  );
}

export function useNewThreadDraft() {
  const context = useContext(NewThreadDraftContext);
  if (!context) {
    throw new Error(
      "useNewThreadDraft must be used within NewThreadDraftProvider",
    );
  }
  return context;
}

export function useStartNewThread() {
  const router = useRouter();
  const pathname = usePathname();

  return useCallback(
    (options?: { agentName?: string | null; replace?: boolean }) => {
      if (isNewThreadPathname(pathname)) {
        return false;
      }

      const route = pathOfNewThread({
        currentSearch:
          typeof window === "undefined" ? undefined : window.location.search,
        agentName: options?.agentName ?? null,
      });

      if (options?.replace) {
        router.replace(route);
      } else {
        router.push(route);
      }
      return true;
    },
    [pathname, router],
  );
}

import {
  createContext,
  useCallback,
  useContext,
  useState,
  type Dispatch,
  type ReactNode,
  type SetStateAction,
} from "react";

import { useSidebar } from "@/components/ui/sidebar";
import type { BrowserOssSource } from "@/core/oss";
import { env } from "@/env";

export interface ArtifactSource {
  filepath: string;
  browserOssSource?: BrowserOssSource | null;
}

export interface ArtifactsContextType {
  artifacts: Record<string, string>;
  setArtifacts: Dispatch<SetStateAction<Record<string, string>>>;
  setArtifactSourcesForThread: (
    threadId: string,
    sources: ArtifactSource[],
  ) => void;
  getArtifactSource: (
    threadId: string,
    filepath: string,
  ) => ArtifactSource | null;

  selectedArtifact: string | null;
  autoSelect: boolean;
  select: (artifact: string, autoSelect?: boolean) => void;
  deselect: () => void;

  open: boolean;
  autoOpen: boolean;
  setOpen: (open: boolean) => void;
  hasTransientArtifactAutoOpened: (artifactId: string) => boolean;
  markTransientArtifactAutoOpened: (artifactId: string) => void;
}

const ArtifactsContext = createContext<ArtifactsContextType | undefined>(
  undefined,
);

interface ArtifactsProviderProps {
  children: ReactNode;
}

export function ArtifactsProvider({ children }: ArtifactsProviderProps) {
  const [artifacts, setArtifacts] = useState<Record<string, string>>({});
  const [artifactSourcesByThread, setArtifactSourcesByThread] = useState<
    Record<string, Record<string, ArtifactSource>>
  >({});
  const [selectedArtifact, setSelectedArtifact] = useState<string | null>(null);
  const [autoSelect, setAutoSelect] = useState(true);
  const [open, setOpen] = useState(
    env.NEXT_PUBLIC_STATIC_WEBSITE_ONLY === "true",
  );
  const [autoOpen, setAutoOpen] = useState(true);
  const [autoOpenedTransientArtifacts, setAutoOpenedTransientArtifacts] =
    useState<Set<string>>(() => new Set());
  const { setOpen: setSidebarOpen } = useSidebar();

  const select = useCallback(
    (artifact: string, autoSelect = false) => {
      setSelectedArtifact(artifact);
      if (env.NEXT_PUBLIC_STATIC_WEBSITE_ONLY !== "true") {
        setSidebarOpen(false);
      }
      if (!autoSelect) {
        setAutoSelect(false);
      }
    },
    [setSidebarOpen, setSelectedArtifact, setAutoSelect],
  );

  const deselect = useCallback(() => {
    setSelectedArtifact(null);
    setAutoSelect(true);
    setOpen(false);
  }, []);

  const setArtifactSourcesForThread = useCallback(
    (threadId: string, sources: ArtifactSource[]) => {
      const nextSources = Object.fromEntries(
        sources.map((source) => [source.filepath, source]),
      );

      setArtifactSourcesByThread((currentSources) => {
        const currentThreadSources = currentSources[threadId] ?? {};
        const currentKeys = Object.keys(currentThreadSources);
        const nextKeys = Object.keys(nextSources);
        const isUnchanged =
          currentKeys.length === nextKeys.length &&
          nextKeys.every((key) => {
            const currentSource = currentThreadSources[key];
            const nextSource = nextSources[key];
            return (
              currentSource?.filepath === nextSource?.filepath &&
              currentSource?.browserOssSource?.ossUri ===
                nextSource?.browserOssSource?.ossUri &&
              currentSource?.browserOssSource?.objectKey ===
                nextSource?.browserOssSource?.objectKey
            );
          });

        if (isUnchanged) {
          return currentSources;
        }

        return {
          ...currentSources,
          [threadId]: nextSources,
        };
      });
    },
    [],
  );

  const getArtifactSource = useCallback(
    (threadId: string, filepath: string) => {
      return artifactSourcesByThread[threadId]?.[filepath] ?? null;
    },
    [artifactSourcesByThread],
  );

  const hasTransientArtifactAutoOpened = useCallback(
    (artifactId: string) => autoOpenedTransientArtifacts.has(artifactId),
    [autoOpenedTransientArtifacts],
  );

  const markTransientArtifactAutoOpened = useCallback((artifactId: string) => {
    setAutoOpenedTransientArtifacts((currentArtifacts) => {
      if (currentArtifacts.has(artifactId)) {
        return currentArtifacts;
      }

      const nextArtifacts = new Set(currentArtifacts);
      nextArtifacts.add(artifactId);
      return nextArtifacts;
    });
  }, []);

  const value: ArtifactsContextType = {
    artifacts,
    setArtifacts,
    setArtifactSourcesForThread,
    getArtifactSource,

    open,
    autoOpen,
    autoSelect,
    setOpen: (isOpen: boolean) => {
      if (!isOpen && autoOpen) {
        setAutoOpen(false);
        setAutoSelect(false);
      }
      setOpen(isOpen);
    },
    hasTransientArtifactAutoOpened,
    markTransientArtifactAutoOpened,

    selectedArtifact,
    select,
    deselect,
  };

  return (
    <ArtifactsContext.Provider value={value}>
      {children}
    </ArtifactsContext.Provider>
  );
}

export function useArtifacts() {
  const context = useContext(ArtifactsContext);
  if (context === undefined) {
    throw new Error("useArtifacts must be used within an ArtifactsProvider");
  }
  return context;
}

import { DownloadIcon } from "lucide-react";
import { useCallback } from "react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardAction,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { urlOfArtifact } from "@/core/artifacts/utils";
import { useI18n } from "@/core/i18n/hooks";
import {
  getFileExtensionDisplayName,
  getFileIcon,
  getFileName,
} from "@/core/utils/files";
import { cn } from "@/lib/utils";

import { useArtifacts } from "./context";

export function ArtifactFileList({
  className,
  files,
  threadId,
}: {
  className?: string;
  files: Record<string, string>;
  threadId: string;
}) {
  const { t } = useI18n();
  const { select: selectArtifact, setOpen } = useArtifacts();
  const fileEntries = Object.entries(files);

  const handleClick = useCallback(
    (filepath: string) => {
      selectArtifact(filepath);
      setOpen(true);
    },
    [selectArtifact, setOpen],
  );

  return (
    <ul className={cn("flex w-full flex-col gap-4", className)}>
      {fileEntries.map(([filepath]) => (
        <Card
          key={filepath}
          className="relative cursor-pointer p-3"
          onClick={() => handleClick(filepath)}
        >
          <CardHeader className="pr-2 pl-1">
            <CardTitle className="relative pl-8">
              <div>{getFileName(filepath)}</div>
              <div className="absolute top-2 -left-0.5">
                {getFileIcon(filepath, "size-6")}
              </div>
            </CardTitle>
            <CardDescription className="pl-8 text-xs">
              {getFileExtensionDisplayName(filepath)} file
            </CardDescription>
            <CardAction>
              <a
                href={urlOfArtifact({
                  filepath,
                  threadId: threadId,
                  download: true,
                })}
                target="_blank"
                rel="noopener noreferrer"
                onClick={(e) => e.stopPropagation()}
              >
                <Button variant="ghost">
                  <DownloadIcon className="size-4" />
                  {t.common.download}
                </Button>
              </a>
            </CardAction>
          </CardHeader>
        </Card>
      ))}
    </ul>
  );
}

"use client";

import { FileText } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useI18n } from "@/core/i18n/hooks";

import { Tooltip } from "./tooltip";

export function WorkspaceFilesTrigger({ onClick }: { onClick: () => void }) {
  const { t } = useI18n();

  return (
    <Tooltip content={t.workspaceFiles.title}>
      <Button
        className="text-muted-foreground hover:text-foreground"
        variant="ghost"
        onClick={onClick}
      >
        <FileText />
        {t.workspaceFiles.files}
      </Button>
    </Tooltip>
  );
}

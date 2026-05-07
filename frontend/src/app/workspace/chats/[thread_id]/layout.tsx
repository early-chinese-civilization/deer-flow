"use client";

import { PromptInputProvider } from "@/components/ai-elements/prompt-input";
import { ArtifactsProvider } from "@/components/workspace/artifacts";
import { SubtasksProvider } from "@/core/tasks/context";
import { MAX_COMPOSER_UPLOAD_FILE_SIZE_BYTES } from "@/core/uploads/composer-core";

export default function ChatLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <SubtasksProvider>
      <ArtifactsProvider>
        <PromptInputProvider maxFileSize={MAX_COMPOSER_UPLOAD_FILE_SIZE_BYTES}>
          {children}
        </PromptInputProvider>
      </ArtifactsProvider>
    </SubtasksProvider>
  );
}

import type { Message } from "@langchain/langgraph-sdk";

import {
  extractContentFromMessage,
  parseUploadedFiles,
  type FileInMessage,
} from "../messages/utils";

export interface PendingUploadedFiles {
  fromIndex: number;
  files: FileInMessage[];
}

interface PendingUploadedFilesResult {
  messages: Message[];
  hasServerHumanMessage: boolean;
  hasPersistedFiles: boolean;
}

function readStructuredFiles(message: Message): FileInMessage[] | null {
  const files = message.additional_kwargs?.files;
  if (!Array.isArray(files) || files.length === 0) {
    return null;
  }

  return files as FileInMessage[];
}

function hasPersistedFiles(message: Message): boolean {
  if (readStructuredFiles(message)) {
    return true;
  }

  const content = extractContentFromMessage(message);
  return parseUploadedFiles(content).length > 0;
}

function findPendingHumanMessageIndex(
  messages: Message[],
  fromIndex: number,
): number {
  for (
    let index = Math.max(0, fromIndex);
    index < messages.length;
    index += 1
  ) {
    if (messages[index]?.type === "human") {
      return index;
    }
  }

  return -1;
}

export function applyPendingUploadedFiles(
  messages: Message[],
  pending: PendingUploadedFiles | null,
): PendingUploadedFilesResult {
  if (!pending || pending.files.length === 0) {
    return {
      messages,
      hasServerHumanMessage: false,
      hasPersistedFiles: false,
    };
  }

  const targetIndex = findPendingHumanMessageIndex(messages, pending.fromIndex);
  if (targetIndex < 0) {
    return {
      messages,
      hasServerHumanMessage: false,
      hasPersistedFiles: false,
    };
  }

  const targetMessage = messages[targetIndex];
  if (!targetMessage) {
    return {
      messages,
      hasServerHumanMessage: false,
      hasPersistedFiles: false,
    };
  }

  if (hasPersistedFiles(targetMessage)) {
    return {
      messages,
      hasServerHumanMessage: true,
      hasPersistedFiles: true,
    };
  }

  const nextMessages = messages.slice();
  nextMessages[targetIndex] = {
    ...targetMessage,
    additional_kwargs: {
      ...(targetMessage.additional_kwargs ?? {}),
      files: pending.files,
    },
  };

  return {
    messages: nextMessages,
    hasServerHumanMessage: true,
    hasPersistedFiles: false,
  };
}

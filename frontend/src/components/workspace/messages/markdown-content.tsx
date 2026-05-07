"use client";

import { useMemo } from "react";
import type { AnchorHTMLAttributes } from "react";

import {
  MessageResponse,
  type MessageResponseProps,
} from "@/components/ai-elements/message";
import {
  rewriteMarkdownImageUrls,
  useResolvedOssUrlMap,
} from "@/core/messages/oss-image";
import { streamdownPlugins } from "@/core/streamdown";
import { cn } from "@/lib/utils";

import { CitationLink } from "../citations/citation-link";

function isExternalUrl(href: string | undefined): boolean {
  return !!href && /^https?:\/\//.test(href);
}

export type MarkdownContentProps = {
  content: string;
  isLoading: boolean;
  rehypePlugins: MessageResponseProps["rehypePlugins"];
  className?: string;
  workspaceId?: string | null;
  remarkPlugins?: MessageResponseProps["remarkPlugins"];
  components?: MessageResponseProps["components"];
};

/** Renders markdown content. */
export function MarkdownContent({
  content,
  isLoading,
  rehypePlugins,
  className,
  workspaceId,
  remarkPlugins = streamdownPlugins.remarkPlugins,
  components: componentsFromProps,
}: MarkdownContentProps) {
  const effectiveRemarkPlugins = (remarkPlugins ??
    streamdownPlugins.remarkPlugins ??
    []) as NonNullable<MessageResponseProps["remarkPlugins"]>;
  const resolvedOssUrlMap = useResolvedOssUrlMap(
    workspaceId,
    isLoading ? "" : content,
  );
  const renderedContent = useMemo(
    () => rewriteMarkdownImageUrls(content, resolvedOssUrlMap),
    [content, resolvedOssUrlMap],
  );

  const components = useMemo(() => {
    return {
      a: (props: AnchorHTMLAttributes<HTMLAnchorElement>) => {
        if (typeof props.children === "string") {
          const match = /^citation:(.+)$/.exec(props.children);
          if (match) {
            const [, text] = match;
            return <CitationLink {...props}>{text}</CitationLink>;
          }
        }
        const { className, target, rel, ...rest } = props;
        const resolvedHref =
          (typeof props.href === "string" && resolvedOssUrlMap[props.href]) ||
          props.href;
        const external = isExternalUrl(resolvedHref);
        return (
          <a
            {...rest}
            className={cn(
              "text-primary decoration-primary/30 hover:decoration-primary/60 underline underline-offset-2 transition-colors",
              className,
            )}
            href={resolvedHref}
            target={target ?? (external ? "_blank" : undefined)}
            rel={rel ?? (external ? "noopener noreferrer" : undefined)}
          />
        );
      },
      ...componentsFromProps,
    };
  }, [componentsFromProps, resolvedOssUrlMap]);

  if (!content) return null;

  return (
    <MessageResponse
      className={className}
      remarkPlugins={effectiveRemarkPlugins}
      rehypePlugins={rehypePlugins}
      components={components}
    >
      {renderedContent}
    </MessageResponse>
  );
}

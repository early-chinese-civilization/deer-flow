import type { Element, ElementContent, Root } from "hast";
import rehypeKatex from "rehype-katex";
import rehypeRaw from "rehype-raw";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import type { StreamdownProps } from "streamdown";
import { visit } from "unist-util-visit";
import type { BuildVisitor } from "unist-util-visit";

type MdastNode = {
  type: string;
  children?: MdastNode[];
  value?: unknown;
  [key: string]: unknown;
};

type MdastRoot = MdastNode & {
  type: "root";
  children: MdastNode[];
};

type MdastText = MdastNode & {
  type: "text";
  value: string;
};

type MdastParent = MdastNode & {
  children: MdastNode[];
};

function isMdastText(node: MdastNode): node is MdastText {
  return node.type === "text" && typeof node.value === "string";
}

function stripTrailingMarkdownPunctuation(value: string) {
  let text = value;
  let suffix = "";

  while (text && ",.;:!?)]}*".includes(text[text.length - 1] ?? "")) {
    suffix = `${text[text.length - 1] ?? ""}${suffix}`;
    text = text.slice(0, -1);
  }

  return { text, suffix };
}

const OSS_URI_RE = /oss:\/\/[^\s<>'"\]]+/g;
const CJK_TEXT_RE =
  /[\p{Script=Han}\p{Script=Hiragana}\p{Script=Katakana}\p{Script=Hangul}]/u;

export function remarkLinkifyOssUris() {
  return (tree: MdastRoot) => {
    visit(
      tree,
      (
        node: MdastNode,
        index: number | undefined,
        parent: MdastParent | undefined,
      ) => {
        if (
          !isMdastText(node) ||
          !parent ||
          typeof index !== "number" ||
          parent.type === "link" ||
          parent.type === "linkReference" ||
          parent.type === "inlineCode" ||
          parent.type === "code"
        ) {
          return;
        }

        const value = node.value;
        if (!OSS_URI_RE.test(value)) {
          OSS_URI_RE.lastIndex = 0;
          return;
        }

        OSS_URI_RE.lastIndex = 0;
        const nextChildren: Array<Record<string, unknown>> = [];
        let lastIndex = 0;
        for (const match of value.matchAll(OSS_URI_RE)) {
          const raw = match[0] ?? "";
          const start = match.index ?? 0;
          if (start > lastIndex) {
            nextChildren.push({
              type: "text",
              value: value.slice(lastIndex, start),
            });
          }

          const { text, suffix } = stripTrailingMarkdownPunctuation(raw);
          if (text) {
            nextChildren.push({
              type: "link",
              url: text,
              children: [{ type: "text", value: text }],
            });
          }
          if (suffix) {
            nextChildren.push({ type: "text", value: suffix });
          }

          lastIndex = start + raw.length;
        }

        if (lastIndex < value.length) {
          nextChildren.push({ type: "text", value: value.slice(lastIndex) });
        }

        if (nextChildren.length > 0 && Array.isArray(parent.children)) {
          parent.children.splice(
            index,
            1,
            ...(nextChildren as unknown as typeof parent.children),
          );
          return index + nextChildren.length;
        }
      },
    );
  };
}

function rehypeSplitWordsIntoSpansLocal() {
  return (tree: Root) => {
    visit(tree, "element", ((node: Element) => {
      if (
        ["p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "strong"].includes(
          node.tagName,
        ) &&
        node.children
      ) {
        const newChildren: Array<ElementContent> = [];
        node.children.forEach((child) => {
          if (child.type === "text") {
            if (CJK_TEXT_RE.test(child.value)) {
              newChildren.push(child);
              return;
            }
            const segmenter = new Intl.Segmenter("zh", { granularity: "word" });
            const segments = segmenter.segment(child.value);
            const words = Array.from(segments)
              .map((segment) => segment.segment)
              .filter(Boolean);
            words.forEach((word: string) => {
              newChildren.push({
                type: "element",
                tagName: "span",
                properties: {
                  className: "animate-fade-in",
                },
                children: [{ type: "text", value: word }],
              });
            });
          } else {
            newChildren.push(child);
          }
        });
        node.children = newChildren;
      }
    }) as BuildVisitor<Root, "element">);
  };
}

export const streamdownPlugins = {
  remarkPlugins: [
    remarkLinkifyOssUris,
    remarkGfm,
    [remarkMath, { singleDollarTextMath: true }],
  ] as StreamdownProps["remarkPlugins"],
  rehypePlugins: [
    rehypeRaw,
    [rehypeKatex, { output: "html" }],
  ] as StreamdownProps["rehypePlugins"],
};

export const streamdownPluginsWithWordAnimation = {
  remarkPlugins: [
    remarkLinkifyOssUris,
    remarkGfm,
    [remarkMath, { singleDollarTextMath: true }],
  ] as StreamdownProps["remarkPlugins"],
  rehypePlugins: [
    [rehypeKatex, { output: "html" }],
    rehypeSplitWordsIntoSpansLocal,
  ] as StreamdownProps["rehypePlugins"],
};

// Plugins for human messages - keep markdown limited, but still linkify oss:// references.
export const humanMessagePlugins = {
  remarkPlugins: [
    remarkLinkifyOssUris,
    // Only include math support for human messages
    [remarkMath, { singleDollarTextMath: true }],
  ] as StreamdownProps["remarkPlugins"],
  rehypePlugins: [
    [rehypeKatex, { output: "html" }],
  ] as StreamdownProps["rehypePlugins"],
};

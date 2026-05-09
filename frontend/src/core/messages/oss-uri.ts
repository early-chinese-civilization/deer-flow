const TRAILING_MARKDOWN_PUNCTUATION = ",.;:!?)]}*";

export function stripTrailingMarkdownPunctuation(value: string) {
  let text = value;
  let suffix = "";

  while (
    text &&
    TRAILING_MARKDOWN_PUNCTUATION.includes(text[text.length - 1] ?? "")
  ) {
    suffix = `${text[text.length - 1] ?? ""}${suffix}`;
    text = text.slice(0, -1);
  }

  return { text, suffix };
}

export function normalizeOssUriCandidate(value: string) {
  return stripTrailingMarkdownPunctuation(value).text;
}

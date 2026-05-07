const CODE_FILE_EXTENSIONS = new Set([
  "txt",
  "csv",
  "log",
  "conf",
  "config",
  "properties",
  "props",
  "js",
  "jsx",
  "ts",
  "tsx",
  "mjs",
  "cjs",
  "mts",
  "cts",
  "html",
  "htm",
  "css",
  "scss",
  "sass",
  "less",
  "vue",
  "svelte",
  "astro",
  "py",
  "pyi",
  "pyw",
  "java",
  "kt",
  "kts",
  "scala",
  "groovy",
  "c",
  "h",
  "cpp",
  "cc",
  "cxx",
  "hpp",
  "hxx",
  "hh",
  "cs",
  "go",
  "rs",
  "rb",
  "rake",
  "php",
  "sh",
  "bash",
  "zsh",
  "fish",
  "json",
  "jsonc",
  "json5",
  "yaml",
  "yml",
  "toml",
  "xml",
  "ini",
  "env",
  "md",
  "mdx",
  "rst",
  "sql",
  "swift",
  "dart",
  "lua",
  "r",
  "matlab",
  "julia",
  "jl",
  "elm",
  "haskell",
  "hs",
  "elixir",
  "ex",
  "clj",
  "cljs",
  "dockerfile",
  "docker",
  "tf",
  "tfvars",
  "hcl",
  "makefile",
  "cmake",
  "gradle",
  "gitignore",
  "gitattributes",
  "graphql",
  "gql",
  "proto",
  "prisma",
  "wasm",
  "zig",
  "v",
  "skill",
]);

const UNSUPPORTED_PREVIEW_EXTENSIONS = new Set([
  "doc",
  "docx",
  "ppt",
  "pptx",
  "xls",
  "xlsx",
]);
const RICH_PREVIEW_EXTENSIONS = new Set(["md", "mdx", "html", "htm", "skill"]);
const IFRAME_PREVIEW_EXTENSIONS = new Set([
  "pdf",
  "mp3",
  "wav",
  "ogg",
  "m4a",
  "mp4",
  "webm",
  "mov",
  "m4v",
]);
const IMAGE_PREVIEW_EXTENSIONS = new Set([
  "png",
  "jpg",
  "jpeg",
  "gif",
  "webp",
  "bmp",
  "ico",
  "tiff",
  "heic",
]);
const ACTIVE_CONTENT_PREVIEW_EXTENSIONS = new Set(["svg"]);

export type ArtifactDisplayMode =
  | "code"
  | "rich-preview"
  | "image-preview"
  | "iframe-preview"
  | "unsupported-preview";

function getFileExtension(filepath: string) {
  const filename = filepath.split("/").pop() ?? filepath;
  const dotIndex = filename.lastIndexOf(".");
  if (dotIndex <= 0 || dotIndex === filename.length - 1) {
    return "";
  }
  return filename.slice(dotIndex + 1).toLowerCase();
}

export function getArtifactDisplayMode(filepath: string): ArtifactDisplayMode {
  const extension = getFileExtension(filepath);

  if (UNSUPPORTED_PREVIEW_EXTENSIONS.has(extension)) {
    return "unsupported-preview";
  }

  if (
    RICH_PREVIEW_EXTENSIONS.has(extension) ||
    ACTIVE_CONTENT_PREVIEW_EXTENSIONS.has(extension)
  ) {
    return "rich-preview";
  }

  if (IMAGE_PREVIEW_EXTENSIONS.has(extension)) {
    return "image-preview";
  }

  if (CODE_FILE_EXTENSIONS.has(extension)) {
    return "code";
  }

  if (IFRAME_PREVIEW_EXTENSIONS.has(extension)) {
    return "iframe-preview";
  }

  return "unsupported-preview";
}

export function getSvgPreviewDataUrl(content: string): string | null {
  const trimmedContent = content.trim();
  if (!/<svg(?:\s|>)/i.test(trimmedContent)) {
    return null;
  }

  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(trimmedContent)}`;
}

export function shouldShowArtifactCodePreviewToggle({
  displayMode,
  isSvgPreview,
}: {
  displayMode: ArtifactDisplayMode;
  isSvgPreview: boolean;
}): boolean {
  return displayMode === "rich-preview" && !isSvgPreview;
}

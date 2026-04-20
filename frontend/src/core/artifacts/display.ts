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

export type ArtifactDisplayMode =
  | "code"
  | "rich-preview"
  | "iframe-preview"
  | "unsupported-preview";

function getFileExtension(filepath: string) {
  const filename = filepath.split("/").pop() ?? filepath;
  const lastSegment = filename.split(".").pop();
  if (!lastSegment) {
    return "";
  }
  return lastSegment.toLowerCase();
}

export function getArtifactDisplayMode(filepath: string): ArtifactDisplayMode {
  const extension = getFileExtension(filepath);

  if (UNSUPPORTED_PREVIEW_EXTENSIONS.has(extension)) {
    return "unsupported-preview";
  }

  if (RICH_PREVIEW_EXTENSIONS.has(extension)) {
    return "rich-preview";
  }

  if (CODE_FILE_EXTENSIONS.has(extension)) {
    return "code";
  }

  return "iframe-preview";
}

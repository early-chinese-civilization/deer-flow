import assert from "node:assert/strict";
import test from "node:test";

const { parseUploadedFiles } = await import(
  new URL("./utils.ts", import.meta.url).href
);

void test("parses uploaded files with explicit sandbox paths", () => {
  const files = parseUploadedFiles(`
<uploaded_files>
- report.md (42 B)
  Path: /mnt/user-data/uploads/report.md
</uploaded_files>
`);

  assert.deepEqual(files, [
    {
      filename: "report.md",
      size: 42,
      path: "/mnt/user-data/uploads/report.md",
      virtual_path: "/mnt/user-data/uploads/report.md",
    },
  ]);
});

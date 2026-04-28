import assert from "node:assert/strict";
import test from "node:test";

const { addObservedWorkspaceFilesToList } = await import(
  new URL("./cache.ts", import.meta.url).href
);

void test("keeps oss identities on observed workspace file placeholders", () => {
  const current = {
    root_label: "Workspace",
    root_path: "/mnt/user-data",
    files: [],
    tree: [],
    count: 0,
  };

  const next = addObservedWorkspaceFilesToList(current, [
    "/mnt/user-data/uploads/report.md",
  ]);

  assert.equal(next?.files[0]?.oss_uri, null);
  assert.equal(next?.files[0]?.markdown_oss_uri, null);
  assert.equal(next?.files[0]?.virtual_path, "/mnt/user-data/uploads/report.md");
});

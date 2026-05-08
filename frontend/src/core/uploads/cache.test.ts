import assert from "node:assert/strict";
import test from "node:test";

process.env.NEXT_PUBLIC_BASE_PATH = "/deer-flow";

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
  assert.equal(
    next?.files[0]?.virtual_path,
    "/mnt/user-data/uploads/report.md",
  );
});

void test("adds stable backend download source for observed workspace outputs", () => {
  const current = {
    root_label: "Workspace",
    root_path: "/mnt/user-data",
    files: [],
    tree: [],
    count: 0,
  };

  const next = addObservedWorkspaceFilesToList(
    current,
    ["/mnt/user-data/outputs/result.md"],
    { workspaceId: "11111111-1111-1111-1111-111111111111" },
  );

  assert.equal(
    next?.files[0]?.object_key,
    "workspaces/11111111-1111-1111-1111-111111111111/outputs/result.md",
  );
  assert.equal(
    next?.files[0]?.http_uri,
    "/deer-flow/api/workspaces/11111111-1111-1111-1111-111111111111/uploads/content?object_key=workspaces%2F11111111-1111-1111-1111-111111111111%2Foutputs%2Fresult.md",
  );
});

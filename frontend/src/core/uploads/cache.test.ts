import assert from "node:assert/strict";
import test from "node:test";

const {
  addObservedWorkspaceFilesToList,
  normalizeUploadedFilesList,
} = await import(new URL("./cache.ts", import.meta.url).href);

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

void test("adds base path to workspace file content urls in list and tree", () => {
  const originalBasePath = process.env.NEXT_PUBLIC_BASE_PATH;
  process.env.NEXT_PUBLIC_BASE_PATH = "/deer-flow";

  try {
    const next = normalizeUploadedFilesList({
      root_label: "Workspace",
      root_path: "/mnt/user-data",
      count: 1,
      files: [
        {
          filename: "gold_price_chart.png",
          size: 123,
          path: "/mnt/user-data/outputs/gold_price_chart.png",
          virtual_path: "/mnt/user-data/outputs/gold_price_chart.png",
          relative_path: "outputs/gold_price_chart.png",
          artifact_url:
            "/api/workspaces/ws-123/uploads/content?object_key=workspaces%2Fws-123%2Foutputs%2Fgold_price_chart.png",
          http_uri: null,
          oss_uri: "oss://demo-bucket/workspaces/ws-123/outputs/gold_price_chart.png",
          object_key: "workspaces/ws-123/outputs/gold_price_chart.png",
        },
      ],
      tree: [],
    });

    const expectedUrl =
      "/deer-flow/api/workspaces/ws-123/uploads/content?object_key=workspaces%2Fws-123%2Foutputs%2Fgold_price_chart.png";

    assert.equal(next.files[0]?.artifact_url, expectedUrl);
    assert.equal(next.tree[0]?.type, "directory");
    assert.equal(next.tree[0]?.children?.[0]?.artifact_url, expectedUrl);
  } finally {
    if (originalBasePath === undefined) {
      delete process.env.NEXT_PUBLIC_BASE_PATH;
    } else {
      process.env.NEXT_PUBLIC_BASE_PATH = originalBasePath;
    }
  }
});

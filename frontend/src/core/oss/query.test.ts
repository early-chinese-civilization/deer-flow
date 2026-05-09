import assert from "node:assert/strict";
import test from "node:test";

const { getResolvedOssUrlQueryKey, isResolvedOssUrlQueryEnabled } =
  await import(new URL("./query.ts", import.meta.url).href);

void test("builds a stable query key from workspace id and object key", () => {
  assert.deepEqual(
    getResolvedOssUrlQueryKey("ws-123", {
      ossUri: "oss://demo-bucket/workspaces/ws-123/uploads/report.md",
      objectKey: "uploads/report.md",
    }),
    ["oss", "download-url", "ws-123", "uploads/report.md"],
  );
});

void test("disables resolution until both workspace and source exist", () => {
  assert.equal(isResolvedOssUrlQueryEnabled(null, null), false);
  assert.equal(
    isResolvedOssUrlQueryEnabled("ws-123", {
      ossUri: "oss://demo-bucket/workspaces/ws-123/uploads/report.md",
      objectKey: "uploads/report.md",
    }),
    true,
  );
});

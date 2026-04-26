import assert from "node:assert/strict";
import test from "node:test";

const { getBrowserOssSource } = await import(
  new URL("./source.ts", import.meta.url).href
);

void test("maps a file-like object to a browser oss source only when complete", () => {
  assert.deepEqual(
    getBrowserOssSource({
      oss_uri: "oss://demo-bucket/workspaces/ws-123/uploads/report.md",
      object_key: "uploads/report.md",
    }),
    {
      ossUri: "oss://demo-bucket/workspaces/ws-123/uploads/report.md",
      objectKey: "uploads/report.md",
    },
  );

  assert.equal(
    getBrowserOssSource({
      oss_uri: null,
      object_key: "uploads/report.md",
    }),
    null,
  );

  assert.equal(
    getBrowserOssSource({
      oss_uri: "oss://demo-bucket/workspaces/ws-123/uploads/report.md",
      object_key: null,
    }),
    null,
  );
});

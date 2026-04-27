import assert from "node:assert/strict";
import test from "node:test";

const { buildMessageFilesFromAttachments } = await import(
  new URL("./composer-core.ts", import.meta.url).href
);

void test("builds message files with canonical oss path and sandbox path", () => {
  const files = buildMessageFilesFromAttachments([
    {
      uploadState: "uploaded",
      uploadedFile: {
        filename: "report.md",
        size: 42,
        path: "workspace/uploads/report.md",
        virtual_path: "/mnt/user-data/uploads/report.md",
        oss_uri: "oss://demo-bucket/workspaces/ws-1/uploads/report.md",
        object_key: "uploads/report.md",
      },
    },
  ]);

  assert.deepEqual(files, [
    {
      filename: "report.md",
      size: 42,
      path: "oss://demo-bucket/workspaces/ws-1/uploads/report.md",
      virtual_path: "/mnt/user-data/uploads/report.md",
      oss_uri: "oss://demo-bucket/workspaces/ws-1/uploads/report.md",
      object_key: "uploads/report.md",
      status: "uploaded",
    },
  ]);
});

void test("rejects uploaded files without an oss uri", () => {
  assert.throws(
    () =>
      buildMessageFilesFromAttachments([
        {
          uploadState: "uploaded",
          uploadedFile: {
            filename: "report.md",
            size: 42,
            path: "workspace/uploads/report.md",
            virtual_path: "/mnt/user-data/uploads/report.md",
          },
        },
      ]),
    /oss uri/i,
  );
});

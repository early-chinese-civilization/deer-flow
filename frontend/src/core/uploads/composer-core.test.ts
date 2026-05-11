import assert from "node:assert/strict";
import test from "node:test";

const {
  MAX_COMPOSER_UPLOAD_FILE_SIZE_BYTES,
  MAX_COMPOSER_UPLOAD_FILE_SIZE_LABEL,
  buildMessageFilesFromAttachments,
  canSubmitComposerMessage,
  filterComposerUploadFilesBySizeLimit,
  isComposerUploadFileWithinLimit,
  resolveDraftComposerWorkspaceId,
} = await import(new URL("./composer-core.ts", import.meta.url).href);

const { assertCanSubmitComposerMessage } = await import(
  new URL("./composer-core.ts", import.meta.url).href
);

void test("sets the composer upload file size limit to 100MB", () => {
  assert.equal(MAX_COMPOSER_UPLOAD_FILE_SIZE_BYTES, 100 * 1024 * 1024);
  assert.equal(MAX_COMPOSER_UPLOAD_FILE_SIZE_LABEL, "100MB");
});

void test("allows files at the composer upload size limit", () => {
  assert.equal(
    isComposerUploadFileWithinLimit({
      size: MAX_COMPOSER_UPLOAD_FILE_SIZE_BYTES,
    }),
    true,
  );
});

void test("rejects files above the composer upload size limit", () => {
  assert.equal(
    isComposerUploadFileWithinLimit({
      size: MAX_COMPOSER_UPLOAD_FILE_SIZE_BYTES + 1,
    }),
    false,
  );
});

void test("filters oversized composer upload files before they enter attachments", () => {
  const result = filterComposerUploadFilesBySizeLimit([
    { name: "ok.txt", size: MAX_COMPOSER_UPLOAD_FILE_SIZE_BYTES },
    { name: "large.bin", size: MAX_COMPOSER_UPLOAD_FILE_SIZE_BYTES + 1 },
  ]);

  assert.deepEqual(result.accepted, [
    { name: "ok.txt", size: MAX_COMPOSER_UPLOAD_FILE_SIZE_BYTES },
  ]);
  assert.deepEqual(result.rejected, [
    { name: "large.bin", size: MAX_COMPOSER_UPLOAD_FILE_SIZE_BYTES + 1 },
  ]);
});

void test("allows submitting uploaded files without text", () => {
  assert.equal(
    canSubmitComposerMessage({
      text: "",
      attachments: [
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
      ],
    }),
    true,
  );
});

void test("blocks submitting while attachments are still uploading", () => {
  assert.equal(
    canSubmitComposerMessage({
      text: "analyze this",
      attachments: [{ uploadState: "uploading" }],
    }),
    false,
  );
});

void test("blocks empty submissions without uploaded files", () => {
  assert.equal(
    canSubmitComposerMessage({
      text: "",
      attachments: [],
    }),
    false,
  );
});

void test("throws before clearing attachments when uploads block submission", () => {
  assert.throws(
    () =>
      assertCanSubmitComposerMessage({
        text: "analyze this",
        attachments: [{ uploadState: "uploading" }],
      }),
    /not ready/i,
  );
});

void test("builds message files with canonical oss path and sandbox path", () => {
  const files = buildMessageFilesFromAttachments([
    {
      uploadState: "uploaded",
      uploadedFile: {
        filename: "report.md",
        size: 42,
        path: "workspace/uploads/report.md",
        virtual_path: "/mnt/user-data/uploads/report.md",
        http_uri: "/api/threads/ws-1/artifacts/mnt/user-data/uploads/report.md",
        oss_uri: "oss://demo-bucket/workspaces/ws-1/uploads/report.md",
        object_key: "uploads/report.md",
        markdown_http_uri: null,
      },
    },
  ]);

  assert.deepEqual(files, [
    {
      filename: "report.md",
      size: 42,
      path: "oss://demo-bucket/workspaces/ws-1/uploads/report.md",
      virtual_path: "/mnt/user-data/uploads/report.md",
      http_uri: "/api/threads/ws-1/artifacts/mnt/user-data/uploads/report.md",
      oss_uri: "oss://demo-bucket/workspaces/ws-1/uploads/report.md",
      object_key: "uploads/report.md",
      markdown_http_uri: null,
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

void test("keeps the draft workspace only when the draft key matches", () => {
  assert.equal(
    resolveDraftComposerWorkspaceId(
      { draftKey: "draft-a", workspaceId: "workspace-a" },
      "draft-a",
    ),
    "workspace-a",
  );
});

void test("does not reuse a draft workspace for a different draft key", () => {
  assert.equal(
    resolveDraftComposerWorkspaceId(
      { draftKey: "draft-a", workspaceId: "workspace-a" },
      "draft-b",
    ),
    null,
  );
});

void test("does not reuse a draft workspace when the current draft key is empty", () => {
  assert.equal(
    resolveDraftComposerWorkspaceId(
      { draftKey: "draft-a", workspaceId: "workspace-a" },
      null,
    ),
    null,
  );
});

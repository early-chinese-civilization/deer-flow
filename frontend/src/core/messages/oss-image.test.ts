import assert from "node:assert/strict";
import test from "node:test";

const {
  extractOssUris,
  getObjectKeyFromOssUri,
  rewriteMarkdownImageUrls,
} = await import(new URL("./oss-image.ts", import.meta.url).href);

void test("extracts normalized oss uris from markdown content", () => {
  assert.deepEqual(
    extractOssUris(
      "![Photo](oss://demo-bucket/workspaces/ws-123/uploads/photo.png**)\n\nSee oss://demo-bucket/workspaces/ws-123/uploads/photo.png**",
    ),
    ["oss://demo-bucket/workspaces/ws-123/uploads/photo.png"],
  );
});

void test("rewrites markdown image urls to presigned urls", () => {
  assert.equal(
    rewriteMarkdownImageUrls(
      "![Photo](oss://demo-bucket/workspaces/ws-123/uploads/photo.png**)\n\nSee oss://demo-bucket/workspaces/ws-123/uploads/photo.png",
      {
        "oss://demo-bucket/workspaces/ws-123/uploads/photo.png": "https://signed.example/photo.png",
      },
    ),
    "![Photo](https://signed.example/photo.png)\n\nSee oss://demo-bucket/workspaces/ws-123/uploads/photo.png",
  );
});

void test("ignores malformed oss uri encodings", () => {
  assert.equal(
    getObjectKeyFromOssUri("oss://demo-bucket/workspaces/ws-123/uploads/ack%E8%AE%A1%E8%B4%B9.png%"),
    null,
  );
});

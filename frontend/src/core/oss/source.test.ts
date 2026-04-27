import assert from "node:assert/strict";
import test from "node:test";

const { getBrowserOssSource } = await import(
  new URL("./source.ts", import.meta.url).href
);
const { getBrowserOssSourceFromOssUri } = await import(
  new URL("./source.ts", import.meta.url).href
);

void test("maps a file-like object to a browser oss source only when complete", () => {
  assert.deepEqual(
    getBrowserOssSource({
      oss_uri: "oss://demo-bucket/workspaces/ws-123/uploads/report.md",
      object_key: "uploads/report.md",
      artifact_url: "/api/workspaces/ws-123/uploads/content?object_key=uploads%2Freport.md",
    }),
    {
      ossUri: "oss://demo-bucket/workspaces/ws-123/uploads/report.md",
      objectKey: "uploads/report.md",
      httpUri: "/api/workspaces/ws-123/uploads/content?object_key=uploads%2Freport.md",
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

void test("parses an oss uri into a browser oss source", () => {
  assert.deepEqual(
    getBrowserOssSourceFromOssUri(
      "oss://demo-bucket/workspaces/ws-123/uploads/photo%20(1).png",
    ),
    {
      ossUri: "oss://demo-bucket/workspaces/ws-123/uploads/photo%20(1).png",
      objectKey: "workspaces/ws-123/uploads/photo (1).png",
    },
  );
  assert.equal(getBrowserOssSourceFromOssUri("https://example.test"), null);
});

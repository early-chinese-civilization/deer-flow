import assert from "node:assert/strict";
import test from "node:test";

const { normalizeOssUriCandidate } = await import(
  new URL("./oss-uri.ts", import.meta.url).href
);

void test("normalizes trailing markdown punctuation off oss uris", () => {
  assert.equal(
    normalizeOssUriCandidate(
      "oss://ecc-agent-sais/workspaces/ws-1/uploads/ack%E8%AE%A1%E8%B4%B9.png**",
    ),
    "oss://ecc-agent-sais/workspaces/ws-1/uploads/ack%E8%AE%A1%E8%B4%B9.png",
  );
});

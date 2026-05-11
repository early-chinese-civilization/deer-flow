import assert from "node:assert/strict";
import test from "node:test";

const {
  getLegacyDraftQueryValue,
  isNewThreadPathname,
  shouldResetNewThreadDraftKey,
} = await import(new URL("./new-thread-draft-core.ts", import.meta.url).href);

void test("detects the canonical new chat route", () => {
  assert.equal(isNewThreadPathname("/workspace/chats/new"), true);
  assert.equal(isNewThreadPathname("/workspace/chats/thread-id"), false);
});

void test("resets draft key only when entering the new chat route", () => {
  assert.equal(
    shouldResetNewThreadDraftKey(
      "/workspace/chats/thread-id",
      "/workspace/chats/new",
    ),
    true,
  );
  assert.equal(
    shouldResetNewThreadDraftKey(
      "/workspace/chats/new",
      "/workspace/chats/new",
    ),
    false,
  );
  assert.equal(
    shouldResetNewThreadDraftKey(null, "/workspace/chats/new"),
    false,
  );
});

void test("reads legacy draft query values for first-load compatibility", () => {
  assert.equal(getLegacyDraftQueryValue("?draft=legacy-draft"), "legacy-draft");
  assert.equal(getLegacyDraftQueryValue("mode=skill"), null);
});

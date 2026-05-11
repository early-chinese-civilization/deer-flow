import assert from "node:assert/strict";
import test from "node:test";

const { isRecentChatMenuActionVisible } = await import(
  new URL("./recent-chat-actions.ts", import.meta.url).href
);

void test("hides the recent chat share action", () => {
  assert.equal(isRecentChatMenuActionVisible("share"), false);
});

void test("keeps non-share recent chat actions visible", () => {
  assert.equal(isRecentChatMenuActionVisible("rename"), true);
  assert.equal(isRecentChatMenuActionVisible("export"), true);
  assert.equal(isRecentChatMenuActionVisible("delete"), true);
});

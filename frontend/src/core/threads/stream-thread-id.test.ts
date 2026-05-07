import assert from "node:assert/strict";
import test from "node:test";

const { resolveNextStreamThreadId } = await import(
  new URL("./stream-thread-id.ts", import.meta.url).href
);

void test("adopts a persisted thread id after the page-level thread detail gate resolves", () => {
  assert.equal(
    resolveNextStreamThreadId(undefined, "thread-123"),
    "thread-123",
  );
});

void test("resets the managed stream thread id when switching back to a draft thread", () => {
  assert.equal(resolveNextStreamThreadId("thread-123", undefined), null);
});

void test("keeps the current managed stream thread id when it is unchanged", () => {
  assert.equal(
    resolveNextStreamThreadId("thread-123", "thread-123"),
    "thread-123",
  );
});

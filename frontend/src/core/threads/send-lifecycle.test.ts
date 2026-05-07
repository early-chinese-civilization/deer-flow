import assert from "node:assert/strict";
import test from "node:test";

const {
  shouldNotifyThreadStartBeforeEnsureThread,
  shouldShowOptimisticMessageBeforeEnsureThread,
} = await import(new URL("./send-lifecycle.ts", import.meta.url).href);

void test("delays start notification for draft threads until ensureThread completes", () => {
  assert.equal(shouldNotifyThreadStartBeforeEnsureThread(false), false);
});

void test("keeps existing-thread submissions responsive by notifying immediately", () => {
  assert.equal(shouldNotifyThreadStartBeforeEnsureThread(true), true);
});

void test("delays optimistic draft message until the new thread route is ready", () => {
  assert.equal(shouldShowOptimisticMessageBeforeEnsureThread(false), false);
});

void test("keeps optimistic messages immediate for existing threads", () => {
  assert.equal(shouldShowOptimisticMessageBeforeEnsureThread(true), true);
});

import assert from "node:assert/strict";
import test from "node:test";

const { promoteThreadChatState, resolveThreadChatState } = await import(
  new URL("./thread-chat-state.ts", import.meta.url).href
);

const { selectThreadChatState } = await import(
  new URL("./thread-chat-state.ts", import.meta.url).href
);

void test("resolves /new routes to a fresh draft thread state", () => {
  const state = resolveThreadChatState("new", () => "draft-thread-id");

  assert.deepEqual(state, {
    threadId: "draft-thread-id",
    isNewThread: true,
  });
});

void test("resolves persisted routes to a persisted thread state", () => {
  const state = resolveThreadChatState("persisted-thread-id", () => {
    throw new Error(
      "draft id factory should not be called for persisted routes",
    );
  });

  assert.deepEqual(state, {
    threadId: "persisted-thread-id",
    isNewThread: false,
  });
});

void test("promotes a draft chat state to the persisted thread id after first send", () => {
  assert.deepEqual(promoteThreadChatState("persisted-thread-id"), {
    threadId: "persisted-thread-id",
    isNewThread: false,
  });
});

void test("ignores promoted state from another route when opening a new chat", () => {
  const selected = selectThreadChatState({
    routeKey: "new:draft-2",
    routeState: {
      threadId: "draft-thread-id",
      isNewThread: true,
    },
    promoted: {
      routeKey: "persisted:old-thread-id",
      state: {
        threadId: "old-thread-id",
        isNewThread: false,
      },
    },
  });

  assert.deepEqual(selected, {
    threadId: "draft-thread-id",
    isNewThread: true,
  });
});

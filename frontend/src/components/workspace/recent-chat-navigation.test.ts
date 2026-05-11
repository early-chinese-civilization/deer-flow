import assert from "node:assert/strict";
import test from "node:test";

const { getRouteAfterThreadDelete } = await import(
  new URL("./recent-chat-navigation.ts", import.meta.url).href
);

const threads = [
  {
    thread_id: "thread-a",
    metadata: {},
    values: { title: "A" },
  },
  {
    thread_id: "thread-b",
    metadata: {},
    values: { title: "B" },
  },
];

void test("navigates away when the deleted thread is the active route even if params are stale", () => {
  assert.equal(
    getRouteAfterThreadDelete({
      threads,
      deletedThreadId: "thread-a",
      currentRoute: "/workspace/chats/thread-a",
      currentThreadId: "thread-b",
      newThreadRoute: "/workspace/chats/new",
      getThreadRoute: (thread) => `/workspace/chats/${thread.thread_id}`,
    }),
    "/workspace/chats/thread-b",
  );
});

void test("does not navigate when deleting a non-active thread", () => {
  assert.equal(
    getRouteAfterThreadDelete({
      threads,
      deletedThreadId: "thread-b",
      currentRoute: "/workspace/chats/thread-a",
      currentThreadId: "thread-a",
      newThreadRoute: "/workspace/chats/new",
      getThreadRoute: (thread) => `/workspace/chats/${thread.thread_id}`,
    }),
    null,
  );
});

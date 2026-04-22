import assert from "node:assert/strict";
import test from "node:test";

const {
  getThreadAgentName,
  pathOfNewThread,
  pathOfThread,
} = await import(new URL("./utils.ts", import.meta.url).href);

void test("builds draft routes with an agent query", () => {
  assert.equal(
    pathOfNewThread({
      agentName: "hudi",
    }),
    "/workspace/chats/new?agent=hudi",
  );
});

void test("preserves unrelated draft query params while updating the agent", () => {
  assert.equal(
    pathOfNewThread({
      currentSearch: "mode=skill&mock=true",
      agentName: "hudi",
    }),
    "/workspace/chats/new?mode=skill&mock=true&agent=hudi",
  );
});

void test("builds canonical existing-thread routes under the shared chats namespace", () => {
  assert.equal(
    pathOfThread({
      thread_id: "thread-123",
      metadata: {
        agent_name: "hudi",
      },
      values: {},
    }),
    "/workspace/chats/thread-123?agent=hudi",
  );
});

void test("normalizes mismatched existing-thread agent queries while preserving unrelated params", () => {
  assert.equal(
    pathOfThread(
      {
        thread_id: "thread-123",
        metadata: {
          agent_name: "hudi",
        },
        values: {},
      },
      {
        currentPath: "/workspace/chats/thread-123",
        currentSearch: "agent=other&mode=skill&mock=true",
      },
    ),
    "/workspace/chats/thread-123?agent=hudi&mode=skill&mock=true",
  );
});

void test("falls back to values.agent_name for legacy existing threads", () => {
  assert.equal(
    getThreadAgentName({
      metadata: {},
      values: {
        agent_name: "legacy-agent",
      },
    }),
    "legacy-agent",
  );
});

import assert from "node:assert/strict";
import test from "node:test";

process.env.NEXT_PUBLIC_BASE_PATH = "/deer-flow";

const { getThreadAgentName, pathOfNewThread, pathOfThread } = await import(
  new URL("./utils.ts", import.meta.url).href
);

void test("builds draft routes with an agent query", () => {
  assert.equal(
    pathOfNewThread({
      agentName: "hudi",
    }),
    "/deer-flow/workspace/chats/new?agent=hudi",
  );
});

void test("preserves unrelated draft query params while updating the agent", () => {
  assert.equal(
    pathOfNewThread({
      currentSearch: "mode=skill&mock=true",
      agentName: "hudi",
    }),
    "/deer-flow/workspace/chats/new?mode=skill&mock=true&agent=hudi",
  );
});

void test("replaces the draft nonce while preserving unrelated new-chat query params", () => {
  assert.equal(
    pathOfNewThread({
      currentSearch: "mode=skill&draft=old-draft&agent=old-agent",
      agentName: null,
      draftNonce: "new-draft",
    }),
    "/deer-flow/workspace/chats/new?mode=skill&draft=new-draft",
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
    "/deer-flow/workspace/chats/thread-123?agent=hudi",
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
        currentPath: "/deer-flow/workspace/chats/thread-123",
        currentSearch: "agent=other&mode=skill&mock=true",
      },
    ),
    "/deer-flow/workspace/chats/thread-123?agent=hudi&mode=skill&mock=true",
  );
});

void test("promotes a draft route to the persisted thread id without carrying the draft nonce", () => {
  assert.equal(
    pathOfThread("persisted-thread-id", {
      currentPath: "/workspace/chats/new",
      currentSearch: "draft=temp-thread-id&agent=hudi",
      agentName: "hudi",
    }),
    "/deer-flow/workspace/chats/persisted-thread-id?agent=hudi",
  );
});

void test("infers legacy agent routes when current path includes a base path", () => {
  assert.equal(
    pathOfThread("thread-123", {
      currentPath: "/deer-flow/workspace/agents/hudi/chats/thread-123",
      currentSearch: "mock=true",
    }),
    "/deer-flow/workspace/chats/thread-123?mock=true&agent=hudi",
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

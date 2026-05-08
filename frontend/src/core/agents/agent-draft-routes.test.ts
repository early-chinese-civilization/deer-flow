import assert from "node:assert/strict";
import test from "node:test";

process.env.NEXT_PUBLIC_BASE_PATH = "/deer-flow";

const { pathOfCreateAgentDraft, resolveAgentDraftTab } = await import(
  new URL("./agent-draft-routes.ts", import.meta.url).href
);

void test("defaults unknown tabs back to the first draft tab", () => {
  assert.equal(resolveAgentDraftTab("confirm"), "confirm");
  assert.equal(resolveAgentDraftTab("unknown"), "name");
  assert.equal(resolveAgentDraftTab(null), "name");
});

void test("builds create draft routes and preserves unrelated query params", () => {
  assert.equal(
    pathOfCreateAgentDraft(),
    "/deer-flow/workspace/agents/new?tab=name",
  );
  assert.equal(
    pathOfCreateAgentDraft({
      currentSearch: "mode=skill&mock=true",
      tab: "skills",
    }),
    "/deer-flow/workspace/agents/new?mode=skill&mock=true&tab=skills",
  );
});

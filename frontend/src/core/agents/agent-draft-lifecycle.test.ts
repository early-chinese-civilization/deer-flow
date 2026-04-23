import assert from "node:assert/strict";
import test from "node:test";

const {
  canFinalizeAgentDraft,
  isAgentDraftInputComplete,
  isAgentDraftNameReadonly,
  normalizeAgentDraftPayload,
  toAgentDraftPatchRequest,
} = await import(new URL("./agent-draft-lifecycle.ts", import.meta.url).href);

void test("normalizes payloads and removes duplicate skill names while preserving order", () => {
  assert.deepEqual(
    normalizeAgentDraftPayload({
      name: "demo-agent",
      description: "desc",
      soul: "soul",
      skills: ["alpha", "beta", "alpha", " ", "gamma"],
    }),
    {
      name: "demo-agent",
      description: "desc",
      soul: "soul",
      skills: ["alpha", "beta", "gamma"],
    },
  );
});

void test("serializes a full draft snapshot for local persistence/final submit", () => {
  assert.deepEqual(
    toAgentDraftPatchRequest({
      name: "demo-agent",
      description: "desc",
      soul: "soul",
      skills: ["alpha", "alpha", "beta"],
    }),
    {
      name: "demo-agent",
      description: "desc",
      soul: "soul",
      skills: ["alpha", "beta"],
    },
  );
});

void test("create drafts need a name before final submit, edit drafts do not", () => {
  assert.equal(
    canFinalizeAgentDraft("create", {
      name: "",
      description: "",
      soul: "",
      skills: [],
    }),
    false,
  );
  assert.equal(
    canFinalizeAgentDraft("create", {
      name: "ready-agent",
      description: "",
      soul: "",
      skills: [],
    }),
    true,
  );
  assert.equal(
    canFinalizeAgentDraft("edit", {
      name: "",
      description: "",
      soul: "",
      skills: [],
    }),
    true,
  );
  assert.equal(isAgentDraftNameReadonly("edit"), true);
  assert.equal(isAgentDraftNameReadonly("create"), false);
});

void test("tracks which create inputs have been filled", () => {
  const emptyForm = {
    name: "",
    description: "",
    soul: "",
    skills: [],
  };
  const readyForm = {
    name: "demo-agent",
    description: "Helpful summary",
    soul: "You are a focused reviewer.",
    skills: ["review"],
  };

  assert.equal(isAgentDraftInputComplete("name", emptyForm), false);
  assert.equal(isAgentDraftInputComplete("description", emptyForm), false);
  assert.equal(isAgentDraftInputComplete("soul", emptyForm), false);
  assert.equal(isAgentDraftInputComplete("skills", emptyForm), false);

  assert.equal(isAgentDraftInputComplete("name", readyForm), true);
  assert.equal(isAgentDraftInputComplete("description", readyForm), true);
  assert.equal(isAgentDraftInputComplete("soul", readyForm), true);
  assert.equal(isAgentDraftInputComplete("skills", readyForm), true);
});

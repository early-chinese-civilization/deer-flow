import assert from "node:assert/strict";
import test from "node:test";

process.env.NEXT_PUBLIC_BASE_PATH = "/deer-flow";
delete process.env.NEXT_PUBLIC_BACKEND_BASE_URL;
delete process.env.NEXT_PUBLIC_LANGGRAPH_BASE_URL;

const { getBackendBaseURL, getLangGraphBaseURL } = await import(
  new URL("./index.ts", import.meta.url).href
);

void test("uses the configured base path as the default backend base url", () => {
  assert.equal(getBackendBaseURL(), "/deer-flow");
});

void test("uses the configured base path for default langgraph urls", () => {
  assert.equal(
    getLangGraphBaseURL(),
    "http://localhost:2026/deer-flow/api/langgraph",
  );
  assert.equal(
    getLangGraphBaseURL(true),
    "http://localhost:3000/deer-flow/mock/api",
  );
});

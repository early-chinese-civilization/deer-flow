import assert from "node:assert/strict";
import test from "node:test";

const { normalizeBasePath, withBasePathFor, withoutBasePathFor } = await import(
  new URL("./base-path.ts", import.meta.url).href
);

void test("normalizes configured base path values", () => {
  assert.equal(normalizeBasePath(undefined), "");
  assert.equal(normalizeBasePath(""), "");
  assert.equal(normalizeBasePath("/"), "");
  assert.equal(normalizeBasePath("deer-flow/"), "/deer-flow");
  assert.equal(normalizeBasePath("/deer-flow/"), "/deer-flow");
});

void test("adds a base path to root-relative browser routes", () => {
  assert.equal(
    withBasePathFor("/deer-flow", "/workspace"),
    "/deer-flow/workspace",
  );
  assert.equal(
    withBasePathFor("/deer-flow", "/api/auth/me"),
    "/deer-flow/api/auth/me",
  );
  assert.equal(withBasePathFor("/deer-flow", "/"), "/deer-flow");
});

void test("does not duplicate an existing base path", () => {
  assert.equal(
    withBasePathFor("/deer-flow", "/deer-flow/workspace"),
    "/deer-flow/workspace",
  );
  assert.equal(
    withBasePathFor("/deer-flow", "/deer-flow?next=/workspace"),
    "/deer-flow?next=/workspace",
  );
});

void test("leaves non-root-relative and external urls unchanged", () => {
  assert.equal(withBasePathFor("/deer-flow", "workspace"), "workspace");
  assert.equal(
    withBasePathFor("/deer-flow", "https://example.test/file"),
    "https://example.test/file",
  );
  assert.equal(
    withBasePathFor("/deer-flow", "//cdn.example.test/file"),
    "//cdn.example.test/file",
  );
  assert.equal(
    withBasePathFor("/deer-flow", "blob:https://example.test/id"),
    "blob:https://example.test/id",
  );
  assert.equal(
    withBasePathFor("/deer-flow", "data:text/plain,hi"),
    "data:text/plain,hi",
  );
  assert.equal(
    withBasePathFor("/deer-flow", "oss://bucket/key"),
    "oss://bucket/key",
  );
});

void test("removes a configured base path before route matching", () => {
  assert.equal(
    withoutBasePathFor("/deer-flow", "/deer-flow/workspace/chats"),
    "/workspace/chats",
  );
  assert.equal(withoutBasePathFor("/deer-flow", "/deer-flow"), "/");
  assert.equal(
    withoutBasePathFor("/deer-flow", "/workspace/chats"),
    "/workspace/chats",
  );
});

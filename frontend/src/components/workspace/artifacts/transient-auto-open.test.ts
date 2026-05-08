import assert from "node:assert/strict";
import test from "node:test";

const {
  buildTransientArtifactAutoOpenId,
  createTransientArtifactAutoOpenRegistry,
} = await import(new URL("./transient-auto-open.ts", import.meta.url).href);

void test("allows a transient artifact to auto-open only once", () => {
  const registry = createTransientArtifactAutoOpenRegistry();
  const artifactId = buildTransientArtifactAutoOpenId({
    path: "/tmp/report.md",
    messageId: "message-1",
    toolCallId: "tool-1",
  });

  assert.equal(registry.has(artifactId), false);
  registry.mark(artifactId);
  assert.equal(registry.has(artifactId), true);
});

void test("treats a new tool call as a new transient artifact", () => {
  const registry = createTransientArtifactAutoOpenRegistry();
  const firstArtifactId = buildTransientArtifactAutoOpenId({
    path: "/tmp/report.md",
    messageId: "message-1",
    toolCallId: "tool-1",
  });
  const nextArtifactId = buildTransientArtifactAutoOpenId({
    path: "/tmp/report.md",
    messageId: "message-1",
    toolCallId: "tool-2",
  });

  registry.mark(firstArtifactId);

  assert.equal(registry.has(firstArtifactId), true);
  assert.equal(registry.has(nextArtifactId), false);
});

void test("includes thread id in the transient artifact identity when provided", () => {
  const firstThreadArtifactId = buildTransientArtifactAutoOpenId({
    threadId: "thread-1",
    path: "/tmp/report.md",
    messageId: "message-1",
    toolCallId: "tool-1",
  });
  const nextThreadArtifactId = buildTransientArtifactAutoOpenId({
    threadId: "thread-2",
    path: "/tmp/report.md",
    messageId: "message-1",
    toolCallId: "tool-1",
  });

  assert.notEqual(firstThreadArtifactId, nextThreadArtifactId);
});

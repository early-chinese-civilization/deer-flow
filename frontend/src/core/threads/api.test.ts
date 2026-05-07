import assert from "node:assert/strict";
import test from "node:test";

const { isThreadApiError, throwThreadApiError } = await import(
  new URL("./api-error.ts", import.meta.url).href
);

void test("thread API errors preserve response status on failures", async () => {
  await assert.rejects(
    () =>
      throwThreadApiError(
        new Response(JSON.stringify({ detail: "Thread not found" }), {
          status: 404,
          statusText: "Not Found",
          headers: { "Content-Type": "application/json" },
        }),
        "Failed to load thread",
      ),
    (error: unknown) => {
      assert.equal(isThreadApiError(error), true);
      assert.equal((error as { status: number }).status, 404);
      assert.equal((error as Error).message, "Thread not found");
      return true;
    },
  );
});

void test("thread API errors fall back when the response body is not JSON", async () => {
  await assert.rejects(
    () =>
      throwThreadApiError(
        new Response("missing", {
          status: 500,
          statusText: "Server Error",
        }),
        "Failed to load thread",
      ),
    (error: unknown) => {
      assert.equal(isThreadApiError(error), true);
      assert.equal((error as { status: number }).status, 500);
      assert.equal((error as Error).message, "Failed to load thread");
      return true;
    },
  );
});

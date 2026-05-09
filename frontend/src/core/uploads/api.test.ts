import assert from "node:assert/strict";
import test from "node:test";

process.env.NEXT_PUBLIC_BASE_PATH = "/deer-flow";

const { getWorkspaceDownloadUrl } = await import(
  new URL("./api.ts", import.meta.url).href
);

function requestInputToString(input: RequestInfo | URL | undefined): string {
  if (typeof input === "string") {
    return input;
  }
  if (input instanceof URL) {
    return input.toString();
  }
  if (input && typeof input.url === "string") {
    return input.url;
  }
  return "";
}

void test("requests a fresh presigned download url for a workspace file", async () => {
  const originalFetch = globalThis.fetch;
  const calls: Array<[RequestInfo | URL, RequestInit | undefined]> = [];

  globalThis.fetch = (async (input, init) => {
    calls.push([input, init]);
    return new Response(
      JSON.stringify({
        download_url: "https://example.test/download",
        oss_uri: "oss://demo-bucket/workspaces/ws-123/uploads/report.md",
      }),
      {
        status: 200,
        headers: { "Content-Type": "application/json" },
      },
    );
  }) as typeof fetch;

  try {
    const result = await getWorkspaceDownloadUrl("ws-123", "uploads/report.md");

    assert.deepEqual(result, {
      download_url: "https://example.test/download",
      oss_uri: "oss://demo-bucket/workspaces/ws-123/uploads/report.md",
    });
    assert.equal(calls.length, 1);
    const requestUrl = calls[0]?.[0] as string | undefined;
    assert.match(
      requestInputToString(calls[0]?.[0]),
      /\/deer-flow\/api\/workspaces\/ws-123\/uploads\/download-url\?object_key=uploads%2Freport\.md$/,
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});

import assert from "node:assert/strict";
import test from "node:test";

const { resolveWorkspaceDownloadUrl } = await import(
  new URL("./api.ts", import.meta.url).href
);

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
    const result = await resolveWorkspaceDownloadUrl(
      "ws-123",
      "uploads/report.md",
    );

    assert.deepEqual(result, {
      download_url: "https://example.test/download",
      oss_uri: "oss://demo-bucket/workspaces/ws-123/uploads/report.md",
    });
    assert.equal(calls.length, 1);
    const requestInput = calls[0]![0];
    const requestUrl =
      typeof requestInput === "string"
        ? requestInput
        : requestInput instanceof URL
          ? requestInput.toString()
          : requestInput.url;
    assert.match(
      requestUrl,
      /\/api\/workspaces\/ws-123\/uploads\/download-url\?object_key=uploads%2Freport\.md$/,
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});

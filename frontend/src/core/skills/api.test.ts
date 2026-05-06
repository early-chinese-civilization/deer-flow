import assert from "node:assert/strict";
import test from "node:test";

const {
  buildSkillHubInstallCheckRequest,
  buildSkillHubInstallRequest,
  getSkillHubInstallCheckFallbackError,
  getSkillHubInstallFallbackError,
} = await import(new URL("./request.ts", import.meta.url).href);

void test("builds SkillHub install conflict request with install payload semantics", () => {
  const [url, init] = buildSkillHubInstallCheckRequest("", "demo-skill", {
    owner_user_id: 7,
  });

  assert.match(url, /\/api\/skills\/demo-skill\/check-download$/);
  assert.deepEqual(JSON.parse(String(init.body)), {
    owner_user_id: 7,
  });
  assert.equal(init.credentials, "include");
});

void test("builds SkillHub install request through compatibility route payload", () => {
  const [url, init] = buildSkillHubInstallRequest("", "demo-skill", {
    owner_user_id: null,
    overwrite: true,
  });

  assert.match(url, /\/api\/skills\/demo-skill\/download$/);
  assert.deepEqual(JSON.parse(String(init.body)), {
    owner_user_id: null,
    overwrite: true,
  });
  assert.equal(init.credentials, "include");
});

void test("SkillHub install fallback errors use install semantics", () => {
  assert.equal(
    getSkillHubInstallCheckFallbackError("Conflict"),
    "Failed to check skill install: Conflict",
  );
  assert.equal(
    getSkillHubInstallFallbackError("Conflict"),
    "Failed to install skill: Conflict",
  );
});

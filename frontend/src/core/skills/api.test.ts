import assert from "node:assert/strict";
import test from "node:test";

const {
  buildSkillHubInstallCheckRequest,
  buildSkillHubInstallRequest,
  buildSkillForkPackageRequest,
  buildSkillInstallUpdateConfirmRequest,
  buildSkillInstallUpdatePreviewRequest,
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

void test("builds editable fork package request without install route semantics", () => {
  const [url, init] = buildSkillForkPackageRequest("", "demo-skill", {
    owner_user_id: 7,
    skill_definition_id: 42,
  });

  assert.match(url, /\/api\/skills\/demo-skill\/fork-package$/);
  assert.deepEqual(JSON.parse(String(init.body)), {
    owner_user_id: 7,
    skill_definition_id: 42,
  });
  assert.equal(init.method, "POST");
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

void test("builds read-only Skill install update preview request", () => {
  const [url, init] = buildSkillInstallUpdatePreviewRequest("", "demo-skill");

  assert.match(url, /\/api\/skills\/demo-skill\/update-install\/preview$/);
  assert.equal(init.method, "GET");
  assert.equal(init.credentials, "include");
  assert.equal(init.body, undefined);
});

void test("builds Skill install update confirm request for selected version", () => {
  const [url, init] = buildSkillInstallUpdateConfirmRequest("", "demo-skill", {
    skill_version_id: 202,
  });

  assert.match(url, /\/api\/skills\/demo-skill\/update-install$/);
  assert.deepEqual(JSON.parse(String(init.body)), {
    skill_version_id: 202,
  });
  assert.equal(init.method, "POST");
  assert.equal(init.credentials, "include");
});

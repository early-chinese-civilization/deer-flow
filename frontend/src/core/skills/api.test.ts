import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const {
  buildSkillHubInstallRequest,
  buildSkillInstallUpdateConfirmRequest,
  buildSkillInstallUpdatePreviewRequest,
  getSkillHubInstallFallbackError,
} = await import(new URL("./request.ts", import.meta.url).href);

void test("builds terminal Skill install request with composite version identity", () => {
  const [url, init] = buildSkillHubInstallRequest("", {
    skill_id: "12345678-1234-5678-1234-567812345678",
    version_number: 2,
  });

  assert.equal(url, "/api/skills/install");
  assert.deepEqual(JSON.parse(String(init.body)), {
    skill_id: "12345678-1234-5678-1234-567812345678",
    version_number: 2,
  });
  assert.equal(init.method, "POST");
  assert.equal(init.credentials, "include");
});

void test("SkillHub install fallback errors use install semantics", () => {
  assert.equal(
    getSkillHubInstallFallbackError("Conflict"),
    "Failed to install skill: Conflict",
  );
});

void test("install APIs avoid download-named frontend aliases", async () => {
  const [apiSource, hooksSource] = await Promise.all([
    readFile(new URL("./api.ts", import.meta.url), "utf8"),
    readFile(new URL("./hooks.ts", import.meta.url), "utf8"),
  ]);

  assert.doesNotMatch(apiSource, /\bcheckSkillDownload\b/);
  assert.doesNotMatch(
    apiSource,
    /\bdownloadSkill\b|\bdownloadSkillForkPackage\b|\bcheckSkillHubInstall\b/,
  );
  assert.doesNotMatch(
    hooksSource,
    /\buseDownloadSkill\b|\buseDownloadSkillForkPackage\b/,
  );
  assert.doesNotMatch(apiSource, /check-download|fork-package|\/download/);
  assert.match(apiSource, /\binstallSkillHubSkill\b/);
  assert.match(hooksSource, /\buseInstallSkillHubSkill\b/);
});

void test("builds read-only Skill install update preview request", () => {
  const [url, init] = buildSkillInstallUpdatePreviewRequest(
    "",
    "demo-skill",
    301,
  );

  assert.match(
    url,
    /\/api\/skills\/demo-skill\/update-install\/preview\?skill_installation_id=301$/,
  );
  assert.equal(init.method, "GET");
  assert.equal(init.credentials, "include");
  assert.equal(init.body, undefined);
});

void test("builds Skill install update confirm request for selected version", () => {
  const [url, init] = buildSkillInstallUpdateConfirmRequest("", "demo-skill", {
    skill_installation_id: 301,
    skill_id: "12345678-1234-5678-1234-567812345678",
    version_number: 2,
  });

  assert.match(url, /\/api\/skills\/demo-skill\/update-install$/);
  assert.deepEqual(JSON.parse(String(init.body)), {
    skill_installation_id: 301,
    skill_id: "12345678-1234-5678-1234-567812345678",
    version_number: 2,
  });
  assert.equal(init.method, "POST");
  assert.equal(init.credentials, "include");
});

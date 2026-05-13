import assert from "node:assert/strict";
import test from "node:test";

import type { SkillApiResponse } from "./normalization";

const { normalizeSkillFromApi } = await import(
  new URL("./normalization.ts", import.meta.url).href
);

function apiSkill(overrides: Partial<SkillApiResponse>): SkillApiResponse {
  return {
    name: "demo-skill",
    description: "Demo skill",
    license: null,
    enabled: true,
    ...overrides,
  };
}

void test("normalizes temporary legacy Skill relation response literals", () => {
  const downloaded = normalizeSkillFromApi(
    apiSkill({
      viewer_relation: "downloaded",
      skill_install_id: 101,
    }),
  );
  assert.equal(downloaded.viewer_relation, "installed");
  assert.equal(downloaded.skill_installation_id, 101);

  const forked = normalizeSkillFromApi(
    apiSkill({
      source_kind: "fork",
      viewer_relation: "forked",
    }),
  );
  assert.equal(forked.source_kind, "personal");
  assert.equal(forked.viewer_relation, "authored");
});

void test("uses legacy Skill install id only as read-boundary fallback", () => {
  const skill = normalizeSkillFromApi(
    apiSkill({
      space: "personal",
      skill_install_id: 202,
    }),
  );

  assert.equal(skill.skill_installation_id, 202);
  assert.equal(skill.source_kind, "community");
  assert.equal(skill.viewer_relation, "installed");
});

void test("canonical Skill installation id wins over legacy fallback id", () => {
  const skill = normalizeSkillFromApi(
    apiSkill({
      skill_installation_id: 303,
      skill_install_id: 404,
    }),
  );

  assert.equal(skill.skill_installation_id, 303);
});

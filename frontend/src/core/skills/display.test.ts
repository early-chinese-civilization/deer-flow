import assert from "node:assert/strict";
import test from "node:test";

import type { Skill } from "./type";

const {
  findInstalledSkillForSkillHubItem,
  formatPlatformVersion,
  getAgentSkillBindingPlatformVersion,
  getAgentSkillSourceLabel,
  getSkillHubLatestPlatformVersion,
  getSkillInstallState,
  getSkillPlatformVersion,
  isAgentSkillBindingUnavailable,
} = await import(new URL("./display.ts", import.meta.url).href);

function skill(overrides: Partial<Skill>): Skill {
  return {
    name: "demo-skill",
    description: "Demo skill",
    category: "public",
    license: null,
    enabled: true,
    ...overrides,
  };
}

void test("prefers platform version fields over source package metadata", () => {
  assert.equal(
    getSkillPlatformVersion(
      skill({
        platform_version: 3,
        version: "2",
        package_version: "pkg-9",
        release_version: "rel_internal",
      }),
    ),
    3,
  );

  assert.equal(
    getSkillHubLatestPlatformVersion(
      skill({
        latest_platform_version: 5,
        platform_version: 4,
        version: "3",
      }),
    ),
    5,
  );
});

void test("derives SkillHub installed state from matching My Skills row", () => {
  const publicSkill = skill({
    category: "public",
    skill_definition_id: 10,
    platform_version: 2,
  });
  const installedSkill = skill({
    category: "custom",
    skill_definition_id: 10,
    skill_install_id: 20,
    platform_version: 1,
  });

  const match = findInstalledSkillForSkillHubItem(publicSkill, [
    publicSkill,
    installedSkill,
  ]);

  assert.equal(match, installedSkill);
  assert.equal(getSkillInstallState(publicSkill, match), "update-available");
});

void test("uses explicit API update state when provided", () => {
  assert.equal(
    getSkillInstallState(
      skill({
        skill_install_id: 20,
        current_platform_version: 2,
        latest_platform_version: 2,
        update_available: true,
      }),
    ),
    "update-available",
  );
});

void test("reports not-installed when no install identity or version exists", () => {
  assert.equal(
    getSkillInstallState(
      skill({
        category: "public",
        platform_version: 1,
      }),
    ),
    "not-installed",
  );
});

void test("formats Agent skill binding metadata without package metadata", () => {
  assert.equal(formatPlatformVersion(12), "v12");
  assert.equal(formatPlatformVersion("13"), "v13");
  assert.equal(formatPlatformVersion("pkg-ignored"), null);
  assert.equal(
    getAgentSkillBindingPlatformVersion({
      current_platform_version: 4,
    }),
    4,
  );
  assert.equal(
    getAgentSkillSourceLabel({
      source: "my_skills",
      source_label: null,
    }),
    "My Skills",
  );
  assert.equal(
    isAgentSkillBindingUnavailable({
      available: false,
      status: "unavailable",
    }),
    true,
  );
});

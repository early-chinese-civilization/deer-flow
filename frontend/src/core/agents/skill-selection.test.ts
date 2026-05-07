import assert from "node:assert/strict";
import test from "node:test";

import type { Skill } from "../skills/type";

import type { AgentSkillMetadata } from "./types";

const {
  getMetadataDisplaySummary,
  getMetadataSelectionKey,
  getSelectionInstallIds,
  getSelectionSkillNames,
  getSkillDisplaySummary,
  getSkillSelectionKey,
} = await import(new URL("./skill-selection.ts", import.meta.url).href);

const labels = {
  skillhub: "SkillHub",
  mySkills: "My Skills",
  official: "Official",
  unknown: "Unknown source",
  unavailableVersion: "Version unavailable",
};

function skill(overrides: Partial<Skill>): Skill {
  return {
    name: "demo-skill",
    description: "Demo skill",
    category: "custom",
    license: null,
    enabled: true,
    skill_install_id: 201,
    skill_definition_id: 101,
    skill_version_id: 301,
    current_platform_version: 1,
    source_kind: "community",
    viewer_relation: "downloaded",
    owner_display_name: "Demo Publisher",
    ...overrides,
  };
}

function metadata(overrides: Partial<AgentSkillMetadata>): AgentSkillMetadata {
  return {
    name: "demo-skill",
    skill_install_id: 201,
    skill_definition_id: 101,
    skill_version_id: 301,
    current_platform_version: 1,
    source: "skillhub",
    source_label: "Demo Publisher",
    update_available: false,
    available: true,
    status: "available",
    ...overrides,
  };
}

void test("Agent Skill selection rows expose source, installed version, update, and unavailable state", () => {
  assert.deepEqual(getSkillDisplaySummary(skill({}), labels), {
    key: "install:201",
    name: "demo-skill",
    description: "Demo skill",
    versionLabel: "v1",
    sourceLabel: "Demo Publisher",
    updateAvailable: false,
    unavailable: false,
  });

  assert.deepEqual(
    getSkillDisplaySummary(
      skill({
        update_available: true,
        latest_platform_version: 2,
      }),
      labels,
    ),
    {
      key: "install:201",
      name: "demo-skill",
      description: "Demo skill",
      versionLabel: "v1",
      sourceLabel: "Demo Publisher",
      updateAvailable: true,
      unavailable: false,
    },
  );

  assert.deepEqual(
    getSkillDisplaySummary(
      skill({
        skill_version_id: null,
        current_platform_version: null,
      }),
      labels,
    ),
    {
      key: "install:201",
      name: "demo-skill",
      description: "Demo skill",
      versionLabel: "Version unavailable",
      sourceLabel: "Demo Publisher",
      updateAvailable: false,
      unavailable: true,
    },
  );
});

void test("Agent Skill selection rows do not expose package version fallback", () => {
  assert.deepEqual(
    getSkillDisplaySummary(
      skill({
        current_platform_version: null,
        installed_platform_version: null,
        platform_version: null,
        version: "99",
        package_version: "99",
        source_package_version: "99",
      }),
      labels,
    ),
    {
      key: "install:201",
      name: "demo-skill",
      description: "Demo skill",
      versionLabel: "Version unavailable",
      sourceLabel: "Demo Publisher",
      updateAvailable: false,
      unavailable: true,
    },
  );
});

void test("same-name different-source installed Skills remain separate and submit install IDs", () => {
  const alice = skill({
    name: "same-skill",
    skill_install_id: 201,
    skill_definition_id: 101,
    owner_display_name: "Alice",
  });
  const bob = skill({
    name: "same-skill",
    skill_install_id: 202,
    skill_definition_id: 102,
    owner_display_name: "Bob",
  });
  const selection = [getSkillSelectionKey(alice), getSkillSelectionKey(bob)];

  assert.deepEqual(selection, ["install:201", "install:202"]);
  assert.notEqual(
    getSkillDisplaySummary(alice, labels).sourceLabel,
    getSkillDisplaySummary(bob, labels).sourceLabel,
  );
  assert.deepEqual(getSelectionInstallIds(selection), [201, 202]);
  assert.deepEqual(getSelectionSkillNames(selection), []);
});

void test("legacy Agent Skill name fallback remains usable only without install identity", () => {
  const selection = ["name:legacy-skill", "install:201"];

  assert.deepEqual(getSelectionInstallIds(selection), [201]);
  assert.deepEqual(getSelectionSkillNames(selection), ["legacy-skill"]);
});

void test("Agent metadata summaries use platform version and hide internal identity", () => {
  const summary = getMetadataDisplaySummary(
    metadata({
      update_available: true,
    }),
    labels,
  );

  assert.deepEqual(summary, {
    key: "install:201",
    name: "demo-skill",
    description: "",
    versionLabel: "v1",
    sourceLabel: "Demo Publisher",
    updateAvailable: true,
    unavailable: false,
  });
  assert.equal(
    getMetadataSelectionKey(metadata({ skill_install_id: null })),
    "name:demo-skill",
  );
});

void test("Agent metadata summaries render unavailable state", () => {
  assert.deepEqual(
    getMetadataDisplaySummary(
      metadata({
        skill_version_id: null,
        current_platform_version: null,
        update_available: null,
        available: false,
        status: "unavailable",
      }),
      labels,
    ),
    {
      key: "install:201",
      name: "demo-skill",
      description: "",
      versionLabel: "Version unavailable",
      sourceLabel: "Demo Publisher",
      updateAvailable: false,
      unavailable: true,
    },
  );
});

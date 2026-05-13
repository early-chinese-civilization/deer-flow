import assert from "node:assert/strict";
import test from "node:test";

import type { Skill } from "../skills/type";

import type { AgentSkillMetadata } from "./types";

const {
  getAgentSkillSelectionGroups,
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
    skill_id: "12345678-1234-5678-1234-567812345678",
    version_number: 1,
    skill_install_id: 201,
    skill_definition_id: 101,
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
        skill_id: null,
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

void test("Agent Skill selection exposes only install-backed My Skills", () => {
  const installed = skill({
    name: "same-skill",
    space: "personal",
    skill_install_id: 201,
    skill_definition_id: 101,
    owner_display_name: "Alice",
  });
  const system = skill({
    name: "same-skill",
    category: "public",
    space: "system",
    source_kind: "official",
    viewer_relation: "system_available",
    skill_install_id: null,
    skill_definition_id: 501,
    current_platform_version: 3,
    owner_display_name: null,
  });
  const communityNotInstalled = skill({
    name: "community-only",
    category: "public",
    space: "community",
    viewer_relation: "community_available",
    skill_install_id: null,
    skill_definition_id: 601,
    owner_display_name: "Community Author",
  });

  const groups = getAgentSkillSelectionGroups([
    communityNotInstalled,
    system,
    installed,
  ]);

  assert.deepEqual(groups.mySkills.map(getSkillSelectionKey), ["install:201"]);
  assert.notEqual(
    getSkillSelectionKey(installed),
    getSkillSelectionKey(system),
  );
});

void test("System Skill rows are unavailable for custom Agent selection", () => {
  assert.deepEqual(
    getSkillDisplaySummary(
      skill({
        category: "public",
        space: "system",
        source_kind: "official",
        viewer_relation: "system_available",
        skill_install_id: null,
        skill_id: "12345678-1234-5678-1234-567812345679",
        version_number: 3,
        skill_definition_id: 502,
        current_platform_version: null,
        owner_display_name: null,
      }),
      labels,
    ),
    {
      key: "unavailable:12345678-1234-5678-1234-567812345679:v3",
      name: "demo-skill",
      description: "Demo skill",
      versionLabel: "Version unavailable",
      sourceLabel: "Official",
      updateAvailable: false,
      unavailable: true,
    },
  );
});

void test("Agent Skill selections never submit name-only fallback values", () => {
  const selection = ["unavailable:legacy-skill", "install:201"];

  assert.deepEqual(getSelectionInstallIds(selection), [201]);
  assert.deepEqual(getSelectionSkillNames(selection), []);
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
    "unavailable:demo-skill",
  );
});

void test("System Agent metadata is display-only and unavailable for custom Agent resubmit", () => {
  const summary = getMetadataDisplaySummary(
    metadata({
      skill_install_id: null,
      skill_definition_id: 501,
      current_platform_version: 3,
      source: "system",
      source_label: "",
    }),
    labels,
  );

  assert.deepEqual(summary, {
    key: "unavailable:demo-skill",
    name: "demo-skill",
    description: "",
    versionLabel: "v3",
    sourceLabel: "Official",
    updateAvailable: false,
    unavailable: false,
  });
});

void test("Agent metadata summaries render unavailable state", () => {
  assert.deepEqual(
    getMetadataDisplaySummary(
      metadata({
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

import assert from "node:assert/strict";
import test from "node:test";

import type { Skill } from "./type";

const {
  findInstalledSkillForSkillHubItem,
  formatPlatformVersion,
  getAgentSkillBindingPlatformVersion,
  getAgentSkillSourceLabel,
  getSkillDisplayContract,
  getSkillIdentityKey,
  getSkillHubLatestPlatformVersion,
  getSkillInstallState,
  getSkillPlatformVersion,
  isAgentSkillBindingUnavailable,
  isSelfAuthoredCommunitySkill,
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

void test("classifies explicit Skills viewer relation matrix", () => {
  const cases: Array<{
    name: string;
    skill: Skill;
    expected: ReturnType<typeof getSkillDisplayContract>;
  }> = [
    {
      name: "official community",
      skill: skill({
        space: "community",
        source_kind: "official",
        viewer_relation: "official_available",
        skill_definition_id: 10,
      }),
      expected: {
        space: "community",
        sourceKind: "official",
        viewerRelation: "official_available",
        identityKey: "definition:10",
      },
    },
    {
      name: "user community",
      skill: skill({
        space: "community",
        source_kind: "community",
        viewer_relation: "community_available",
        skill_definition_id: 11,
      }),
      expected: {
        space: "community",
        sourceKind: "community",
        viewerRelation: "community_available",
        identityKey: "definition:11",
      },
    },
    {
      name: "self-authored community listing",
      skill: skill({
        space: "community",
        source_kind: "community",
        viewer_relation: "authored_published",
        skill_definition_id: 12,
      }),
      expected: {
        space: "community",
        sourceKind: "community",
        viewerRelation: "authored_published",
        identityKey: "definition:12",
      },
    },
    {
      name: "downloaded personal",
      skill: skill({
        category: "custom",
        space: "personal",
        source_kind: "community",
        viewer_relation: "downloaded",
        skill_install_id: 20,
        skill_definition_id: 13,
      }),
      expected: {
        space: "personal",
        sourceKind: "community",
        viewerRelation: "downloaded",
        identityKey: "install:20",
      },
    },
    {
      name: "authored personal",
      skill: skill({
        category: "custom",
        space: "personal",
        source_kind: "personal",
        viewer_relation: "authored",
        skill_install_id: 21,
      }),
      expected: {
        space: "personal",
        sourceKind: "personal",
        viewerRelation: "authored",
        identityKey: "install:21",
      },
    },
    {
      name: "authored published",
      skill: skill({
        category: "custom",
        space: "personal",
        source_kind: "personal",
        viewer_relation: "authored_published",
        skill_install_id: 22,
      }),
      expected: {
        space: "personal",
        sourceKind: "personal",
        viewerRelation: "authored_published",
        identityKey: "install:22",
      },
    },
    {
      name: "authored unpublished changes",
      skill: skill({
        category: "custom",
        space: "personal",
        source_kind: "personal",
        viewer_relation: "authored_unpublished_changes",
        skill_install_id: 23,
      }),
      expected: {
        space: "personal",
        sourceKind: "personal",
        viewerRelation: "authored_unpublished_changes",
        identityKey: "install:23",
      },
    },
    {
      name: "forked",
      skill: skill({
        category: "custom",
        space: "personal",
        source_kind: "fork",
        viewer_relation: "forked",
        skill_install_id: 24,
      }),
      expected: {
        space: "personal",
        sourceKind: "fork",
        viewerRelation: "forked",
        identityKey: "install:24",
      },
    },
    {
      name: "update available",
      skill: skill({
        category: "custom",
        space: "personal",
        source_kind: "community",
        viewer_relation: "update_available",
        skill_install_id: 25,
      }),
      expected: {
        space: "personal",
        sourceKind: "community",
        viewerRelation: "update_available",
        identityKey: "install:25",
      },
    },
  ];

  for (const item of cases) {
    assert.deepEqual(getSkillDisplayContract(item.skill), item.expected);
  }
});

void test("keeps legacy relation fallback centralized", () => {
  assert.deepEqual(
    getSkillDisplayContract(
      skill({
        category: "public",
        owner_user_id: null,
      }),
    ),
    {
      space: "community",
      sourceKind: "official",
      viewerRelation: "official_available",
      identityKey: "legacy:community:official:system:demo-skill",
    },
  );

  assert.deepEqual(
    getSkillDisplayContract(
      skill({
        category: "custom",
        skill_install_id: 20,
      }),
    ),
    {
      space: "personal",
      sourceKind: "community",
      viewerRelation: "downloaded",
      identityKey: "install:20",
    },
  );
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

void test("preserves same-name different-source identity", () => {
  const publicA = skill({
    name: "same-skill",
    skill_definition_id: 100,
    owner_user_id: 8,
  });
  const publicB = skill({
    name: "same-skill",
    skill_definition_id: 101,
    owner_user_id: 9,
  });
  const installedA = skill({
    category: "custom",
    name: "same-skill",
    skill_definition_id: 100,
    skill_install_id: 200,
  });
  const installedB = skill({
    category: "custom",
    name: "same-skill",
    skill_definition_id: 101,
    skill_install_id: 201,
  });

  assert.equal(getSkillIdentityKey(publicA), "definition:100");
  assert.equal(getSkillIdentityKey(publicB), "definition:101");
  assert.equal(getSkillIdentityKey(installedA), "install:200");
  assert.equal(getSkillIdentityKey(installedB), "install:201");
  assert.equal(
    findInstalledSkillForSkillHubItem(publicA, [
      publicA,
      publicB,
      installedA,
      installedB,
    ]),
    installedA,
  );
  assert.equal(
    findInstalledSkillForSkillHubItem(
      skill({
        name: "same-skill",
        skill_definition_id: null,
      }),
      [installedA, installedB],
    ),
    null,
  );
});

void test("uses definition identity for installed Community Space rows", () => {
  const communityRow = skill({
    space: "community",
    source_kind: "community",
    viewer_relation: "update_available",
    skill_definition_id: 100,
    skill_install_id: 200,
  });
  const personalRow = skill({
    category: "custom",
    space: "personal",
    source_kind: "community",
    viewer_relation: "update_available",
    skill_definition_id: 100,
    skill_install_id: 200,
  });

  assert.equal(getSkillIdentityKey(communityRow), "definition:100");
  assert.equal(getSkillIdentityKey(personalRow), "install:200");
  assert.equal(
    getSkillDisplayContract(communityRow).identityKey,
    "definition:100",
  );
  assert.equal(isSelfAuthoredCommunitySkill(communityRow), false);
});

void test("detects self-authored Community listings from explicit relation", () => {
  assert.equal(
    isSelfAuthoredCommunitySkill(
      skill({
        space: "community",
        source_kind: "community",
        viewer_relation: "authored_published",
        skill_definition_id: 300,
      }),
    ),
    true,
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

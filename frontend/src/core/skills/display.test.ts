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
  getSkillWorkspaceCardState,
  isAgentSkillBindingUnavailable,
  isSelfAuthoredCommunitySkill,
  isSystemSkill,
  skillMatchesCommunitySearch,
  skillMatchesWorkspaceSegment,
} = await import(new URL("./display.ts", import.meta.url).href);

function skillId(value: number): string {
  return `00000000-0000-0000-0000-${String(value).padStart(12, "0")}`;
}

function skill(overrides: Partial<Skill>): Skill {
  const hasInstall = overrides.skill_installation_id != null;
  return {
    name: "demo-skill",
    description: "Demo skill",
    space: hasInstall ? "personal" : "community",
    source_kind: "community",
    viewer_relation: hasInstall ? "installed" : "community_available",
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
    space: "community",
    source_kind: "community",
    viewer_relation: "community_available",
    skill_id: skillId(10),
    version_number: 2,
    platform_version: 2,
  });
  const installedSkill = skill({
    skill_id: skillId(10),
    version_number: 1,
    skill_installation_id: 20,
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
      name: "system skill",
      skill: skill({
        space: "system",
        source_kind: "official",
        viewer_relation: "system_available",
        skill_id: skillId(10),
        version_number: 1,
      }),
      expected: {
        space: "system",
        sourceKind: "official",
        viewerRelation: "system_available",
        identityKey: `skill:${skillId(10)}:v1`,
      },
    },
    {
      name: "user community",
      skill: skill({
        space: "community",
        source_kind: "community",
        viewer_relation: "community_available",
        skill_id: skillId(11),
        version_number: 1,
      }),
      expected: {
        space: "community",
        sourceKind: "community",
        viewerRelation: "community_available",
        identityKey: `skill:${skillId(11)}:v1`,
      },
    },
    {
      name: "self-authored community listing",
      skill: skill({
        space: "community",
        source_kind: "community",
        viewer_relation: "authored_published",
        skill_id: skillId(12),
        version_number: 1,
      }),
      expected: {
        space: "community",
        sourceKind: "community",
        viewerRelation: "authored_published",
        identityKey: `skill:${skillId(12)}:v1`,
      },
    },
    {
      name: "installed personal",
      skill: skill({
        space: "personal",
        source_kind: "community",
        viewer_relation: "installed",
        skill_installation_id: 20,
      }),
      expected: {
        space: "personal",
        sourceKind: "community",
        viewerRelation: "installed",
        identityKey: "install:20",
      },
    },
    {
      name: "authored personal",
      skill: skill({
        space: "personal",
        source_kind: "personal",
        viewer_relation: "authored",
        skill_installation_id: 21,
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
        space: "personal",
        source_kind: "personal",
        viewer_relation: "authored_published",
        skill_installation_id: 22,
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
        space: "personal",
        source_kind: "personal",
        viewer_relation: "authored_unpublished_changes",
        skill_installation_id: 23,
      }),
      expected: {
        space: "personal",
        sourceKind: "personal",
        viewerRelation: "authored_unpublished_changes",
        identityKey: "install:23",
      },
    },
    {
      name: "authored personal copy",
      skill: skill({
        space: "personal",
        source_kind: "personal",
        viewer_relation: "authored",
        skill_installation_id: 24,
      }),
      expected: {
        space: "personal",
        sourceKind: "personal",
        viewerRelation: "authored",
        identityKey: "install:24",
      },
    },
    {
      name: "update available",
      skill: skill({
        space: "personal",
        source_kind: "community",
        viewer_relation: "update_available",
        skill_installation_id: 25,
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

void test("normalizes official Community compatibility rows into System surface", () => {
  const officialCompatibilityRow = skill({
    space: "community",
    source_kind: "official",
    viewer_relation: "official_available",
    skill_id: skillId(40),
    version_number: 1,
    platform_version: 1,
  });

  assert.deepEqual(getSkillDisplayContract(officialCompatibilityRow), {
    space: "system",
    sourceKind: "official",
    viewerRelation: "official_available",
    identityKey: `skill:${skillId(40)}:v1`,
  });
  assert.deepEqual(getSkillWorkspaceCardState(officialCompatibilityRow), {
    role: "system",
    primaryAction: "none",
    segments: ["all"],
  });
});

void test("uses explicit API update state when provided", () => {
  assert.equal(
    getSkillInstallState(
      skill({
        skill_installation_id: 20,
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
    skill_id: skillId(100),
    version_number: 1,
    owner_user_id: 8,
  });
  const publicB = skill({
    name: "same-skill",
    skill_id: skillId(101),
    version_number: 1,
    owner_user_id: 9,
  });
  const installedA = skill({
    name: "same-skill",
    skill_id: skillId(100),
    version_number: 1,
    skill_installation_id: 200,
  });
  const installedB = skill({
    name: "same-skill",
    skill_id: skillId(101),
    version_number: 1,
    skill_installation_id: 201,
  });

  assert.equal(getSkillIdentityKey(publicA), `skill:${skillId(100)}:v1`);
  assert.equal(getSkillIdentityKey(publicB), `skill:${skillId(101)}:v1`);
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
        skill_id: null,
      }),
      [installedA, installedB],
    ),
    null,
  );
});

void test("uses terminal Skill identity for Community rows", () => {
  const communityRow = skill({
    space: "community",
    source_kind: "community",
    viewer_relation: "update_available",
    skill_id: skillId(100),
    version_number: 2,
    skill_installation_id: 200,
  });
  const personalRow = skill({
    space: "personal",
    source_kind: "community",
    viewer_relation: "update_available",
    skill_id: skillId(100),
    version_number: 1,
    skill_installation_id: 200,
  });

  assert.equal(getSkillIdentityKey(communityRow), `skill:${skillId(100)}:v2`);
  assert.equal(getSkillIdentityKey(personalRow), "install:200");
  assert.equal(
    getSkillDisplayContract(communityRow).identityKey,
    `skill:${skillId(100)}:v2`,
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
      }),
    ),
    true,
  );
});

void test("classifies authored Personal Space upload with version and publish state", () => {
  const authored = skill({
    space: "personal",
    source_kind: "personal",
    viewer_relation: "authored",
    skill_installation_id: 700,
    platform_version: 1,
  });

  assert.equal(getSkillPlatformVersion(authored), 1);
  assert.deepEqual(getSkillWorkspaceCardState(authored), {
    role: "authored",
    primaryAction: "publish",
    segments: ["all", "authored"],
  });
  assert.equal(skillMatchesWorkspaceSegment(authored, "authored"), true);
  assert.equal(skillMatchesWorkspaceSegment(authored, "installed"), false);
});

void test("published authored Personal Space rows have no no-op manage action", () => {
  const published = skill({
    space: "personal",
    source_kind: "personal",
    viewer_relation: "authored_published",
    skill_installation_id: 702,
    current_platform_version: 2,
  });

  assert.deepEqual(getSkillWorkspaceCardState(published), {
    role: "authored-published",
    primaryAction: "none",
    segments: ["all", "authored"],
  });
  assert.equal(skillMatchesWorkspaceSegment(published, "authored"), true);
  assert.equal(skillMatchesWorkspaceSegment(published, "updates"), false);
});

void test("treats publisher's own Community listing as discovery-only", () => {
  const ownPublishedListing = skill({
    space: "community",
    source_kind: "community",
    viewer_relation: "authored_published",
    platform_version: 1,
  });

  assert.deepEqual(getSkillWorkspaceCardState(ownPublishedListing), {
    role: "self-published-community",
    primaryAction: "none",
    segments: ["all"],
  });
  assert.equal(
    getSkillWorkspaceCardState(ownPublishedListing).primaryAction,
    "none",
  );
});

void test("separates System Skills from Community install rows", () => {
  const systemSkill = skill({
    space: "system",
    source_kind: "official",
    viewer_relation: "system_available",
    owner_display_name: "official",
    skill_id: skillId(801),
    version_number: 2,
    platform_version: 2,
  });
  const userCommunity = skill({
    space: "community",
    source_kind: "community",
    viewer_relation: "community_available",
    owner_display_name: "Demo Publisher",
    skill_id: skillId(802),
    version_number: 3,
    platform_version: 3,
  });

  assert.deepEqual(getSkillWorkspaceCardState(systemSkill), {
    role: "system",
    primaryAction: "none",
    segments: ["all"],
  });
  assert.deepEqual(getSkillWorkspaceCardState(userCommunity), {
    role: "community",
    primaryAction: "add-to-personal",
    segments: ["all"],
  });
  assert.equal(isSystemSkill(systemSkill), true);
  assert.equal(skillMatchesCommunitySearch(systemSkill, "official"), false);
  assert.equal(getSkillHubLatestPlatformVersion(userCommunity), 3);
});

void test("installed Community rows are matched by terminal Skill identity", () => {
  const community = skill({
    space: "community",
    source_kind: "community",
    viewer_relation: "community_available",
    skill_id: skillId(10),
    version_number: 1,
  });
  const installed = skill({
    space: "personal",
    source_kind: "community",
    viewer_relation: "installed",
    skill_id: skillId(10),
    version_number: 1,
    skill_installation_id: 20,
  });

  assert.equal(getSkillInstallState(community, installed), "installed");
});

void test("renders installed relation as Community state", () => {
  const currentInstalled = skill({
    space: "personal",
    source_kind: "community",
    viewer_relation: "installed",
    owner_display_name: "Demo Publisher",
    skill_installation_id: 898,
    current_platform_version: 2,
    latest_platform_version: 2,
    update_available: false,
  });
  const updateAvailable = skill({
    space: "personal",
    source_kind: "community",
    viewer_relation: "update_available",
    owner_display_name: "Demo Publisher",
    skill_installation_id: 901,
    current_platform_version: 1,
    latest_platform_version: 2,
    update_available: true,
  });

  assert.equal(getSkillPlatformVersion(currentInstalled), 2);
  assert.deepEqual(getSkillWorkspaceCardState(currentInstalled), {
    role: "installed",
    primaryAction: "none",
    segments: ["all", "installed"],
  });
  assert.equal(getSkillPlatformVersion(updateAvailable), 1);
  assert.deepEqual(getSkillWorkspaceCardState(updateAvailable), {
    role: "installed",
    primaryAction: "view-update",
    segments: ["all", "installed", "updates"],
  });
  assert.equal(
    skillMatchesWorkspaceSegment(updateAvailable, "installed"),
    true,
  );
  assert.equal(skillMatchesWorkspaceSegment(updateAvailable, "updates"), true);
});

void test("treats authored relation as Personal row", () => {
  const authored = skill({
    space: "personal",
    source_kind: "personal",
    viewer_relation: "authored",
    owner_display_name: "Original Publisher",
    skill_installation_id: 903,
    current_platform_version: 1,
  });

  assert.deepEqual(getSkillWorkspaceCardState(authored), {
    role: "authored",
    primaryAction: "publish",
    segments: ["all", "authored"],
  });
  assert.equal(skillMatchesWorkspaceSegment(authored, "authored"), true);
  assert.equal(skillMatchesWorkspaceSegment(authored, "installed"), false);
});

void test("keeps same-name Community cards distinguishable without user-facing IDs", () => {
  const alice = skill({
    name: "same-skill",
    space: "community",
    source_kind: "community",
    viewer_relation: "community_available",
    owner_display_name: "Alice",
    skill_id: skillId(1000),
    version_number: 1,
  });
  const bob = skill({
    name: "same-skill",
    space: "community",
    source_kind: "community",
    viewer_relation: "community_available",
    owner_display_name: "Bob",
    skill_id: skillId(1001),
    version_number: 1,
  });

  assert.notEqual(getSkillIdentityKey(alice), getSkillIdentityKey(bob));
  assert.equal(alice.owner_display_name, "Alice");
  assert.equal(bob.owner_display_name, "Bob");
  assert.equal(getSkillIdentityKey(alice).startsWith("skill:"), true);
  assert.equal(getSkillIdentityKey(bob).startsWith("skill:"), true);
});

void test("filters Community Space by first-class Skill name and author fields", () => {
  const system = skill({
    name: "deep-research",
    space: "system",
    source_kind: "official",
    viewer_relation: "system_available",
    owner_display_name: "official",
    skill_id: skillId(1100),
    version_number: 1,
  });
  const community = skill({
    name: "deck-builder",
    space: "community",
    source_kind: "community",
    viewer_relation: "community_available",
    owner_display_name: "Avery Chen",
    skill_id: skillId(1101),
    version_number: 1,
  });
  const installedCommunity = skill({
    name: "market-scan",
    space: "community",
    source_kind: "community",
    viewer_relation: "installed",
    owner_display_name: "Mina Park",
    skill_id: skillId(1102),
    version_number: 1,
    skill_installation_id: 2102,
  });
  const updateAvailable = skill({
    name: "analysis-runner",
    space: "community",
    source_kind: "community",
    viewer_relation: "update_available",
    owner_display_name: "Update Publisher",
    skill_id: skillId(1103),
    version_number: 2,
    skill_installation_id: 2103,
    current_platform_version: 1,
    latest_platform_version: 2,
    update_available: true,
  });
  const sameNameAlice = skill({
    name: "duplicate-skill",
    space: "community",
    source_kind: "community",
    viewer_relation: "community_available",
    owner_display_name: "Alice",
    skill_id: skillId(1104),
    version_number: 1,
  });
  const sameNameBob = skill({
    name: "duplicate-skill",
    space: "community",
    source_kind: "community",
    viewer_relation: "community_available",
    owner_display_name: "Bob",
    skill_id: skillId(1105),
    version_number: 1,
  });
  const personalInstalled = skill({
    name: "deck-builder",
    space: "personal",
    source_kind: "community",
    viewer_relation: "installed",
    owner_display_name: "Avery Chen",
    skill_id: skillId(1101),
    version_number: 1,
    skill_installation_id: 2101,
  });
  const rows = [
    system,
    community,
    installedCommunity,
    updateAvailable,
    sameNameAlice,
    sameNameBob,
    personalInstalled,
  ];

  assert.deepEqual(
    rows.filter((row) => skillMatchesCommunitySearch(row, "official")),
    [],
  );
  assert.deepEqual(
    rows.filter((row) => skillMatchesCommunitySearch(row, "avery")),
    [community],
  );
  assert.deepEqual(
    rows.filter((row) => skillMatchesCommunitySearch(row, "market")),
    [installedCommunity],
  );
  assert.deepEqual(
    rows.filter((row) => skillMatchesCommunitySearch(row, "update publisher")),
    [updateAvailable],
  );
  assert.deepEqual(
    rows.filter((row) => skillMatchesCommunitySearch(row, "duplicate-skill")),
    [sameNameAlice, sameNameBob],
  );
  assert.deepEqual(
    rows.filter((row) => skillMatchesCommunitySearch(row, "duplicate Bob")),
    [sameNameBob],
  );
  assert.deepEqual(
    rows.filter((row) => skillMatchesCommunitySearch(row, "community")),
    [community, installedCommunity, updateAvailable, sameNameAlice, sameNameBob],
  );
  assert.deepEqual(
    [
      system,
      community,
      installedCommunity,
      updateAvailable,
      sameNameAlice,
      sameNameBob,
    ].map((row) => ({
      key: getSkillIdentityKey(row),
      state: getSkillWorkspaceCardState(row),
    })),
    [
      {
        key: `skill:${skillId(1100)}:v1`,
        state: {
          role: "system",
          primaryAction: "none",
          segments: ["all"],
        },
      },
      {
        key: `skill:${skillId(1101)}:v1`,
        state: {
          role: "community",
          primaryAction: "add-to-personal",
          segments: ["all"],
        },
      },
      {
        key: `skill:${skillId(1102)}:v1`,
        state: {
          role: "community",
          primaryAction: "none",
          segments: ["all"],
        },
      },
      {
        key: `skill:${skillId(1103)}:v2`,
        state: {
          role: "community",
          primaryAction: "none",
          segments: ["all"],
        },
      },
      {
        key: `skill:${skillId(1104)}:v1`,
        state: {
          role: "community",
          primaryAction: "add-to-personal",
          segments: ["all"],
        },
      },
      {
        key: `skill:${skillId(1105)}:v1`,
        state: {
          role: "community",
          primaryAction: "add-to-personal",
          segments: ["all"],
        },
      },
    ],
  );
  assert.notEqual(
    getSkillIdentityKey(sameNameAlice),
    getSkillIdentityKey(sameNameBob),
  );
});

void test("reports not-installed when no install identity or version exists", () => {
  assert.equal(
    getSkillInstallState(
      skill({
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

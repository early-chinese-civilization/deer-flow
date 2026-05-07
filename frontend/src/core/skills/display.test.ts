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
  skillMatchesCommunitySearch,
  skillMatchesWorkspaceSegment,
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

void test("classifies authored Personal Space upload with version and publish state", () => {
  const authored = skill({
    category: "custom",
    space: "personal",
    source_kind: "personal",
    viewer_relation: "authored",
    skill_install_id: 700,
    skill_definition_id: 600,
    platform_version: 1,
  });

  assert.equal(getSkillPlatformVersion(authored), 1);
  assert.deepEqual(getSkillWorkspaceCardState(authored), {
    role: "authored",
    primaryAction: "publish",
    segments: ["all", "authored"],
  });
  assert.equal(skillMatchesWorkspaceSegment(authored, "authored"), true);
  assert.equal(skillMatchesWorkspaceSegment(authored, "downloaded"), false);
});

void test("uses manage state for publisher's own Community listing", () => {
  const ownPublishedListing = skill({
    space: "community",
    source_kind: "community",
    viewer_relation: "authored_published",
    skill_definition_id: 701,
    platform_version: 1,
  });

  assert.deepEqual(getSkillWorkspaceCardState(ownPublishedListing), {
    role: "self-published-community",
    primaryAction: "manage-published",
    segments: ["all", "authored", "published"],
  });
  assert.equal(
    getSkillWorkspaceCardState(ownPublishedListing).primaryAction,
    "manage-published",
  );
});

void test("uses add-to-Personal-Space action for downloader Community rows", () => {
  const officialCommunity = skill({
    space: "community",
    source_kind: "official",
    viewer_relation: "official_available",
    owner_display_name: "official",
    skill_definition_id: 801,
    platform_version: 2,
  });
  const userCommunity = skill({
    space: "community",
    source_kind: "community",
    viewer_relation: "community_available",
    owner_display_name: "Demo Publisher",
    skill_definition_id: 802,
    platform_version: 3,
  });

  assert.deepEqual(getSkillWorkspaceCardState(officialCommunity), {
    role: "official-community",
    primaryAction: "add-to-personal",
    segments: ["all"],
  });
  assert.deepEqual(getSkillWorkspaceCardState(userCommunity), {
    role: "community",
    primaryAction: "add-to-personal",
    segments: ["all"],
  });
  assert.equal(getSkillHubLatestPlatformVersion(userCommunity), 3);
});

void test("shows downloaded Personal Space rows with version and update state", () => {
  const currentDownloaded = skill({
    category: "custom",
    space: "personal",
    source_kind: "community",
    viewer_relation: "downloaded",
    owner_display_name: "Demo Publisher",
    skill_definition_id: 899,
    skill_install_id: 898,
    current_platform_version: 2,
    latest_platform_version: 2,
    update_available: false,
  });
  const downloaded = skill({
    category: "custom",
    space: "personal",
    source_kind: "community",
    viewer_relation: "update_available",
    owner_display_name: "Demo Publisher",
    skill_definition_id: 900,
    skill_install_id: 901,
    current_platform_version: 1,
    latest_platform_version: 2,
    update_available: true,
  });

  assert.equal(getSkillPlatformVersion(currentDownloaded), 2);
  assert.deepEqual(getSkillWorkspaceCardState(currentDownloaded), {
    role: "downloaded",
    primaryAction: "none",
    segments: ["all", "downloaded"],
  });
  assert.equal(getSkillPlatformVersion(downloaded), 1);
  assert.deepEqual(getSkillWorkspaceCardState(downloaded), {
    role: "downloaded",
    primaryAction: "view-update",
    segments: ["all", "downloaded", "updates"],
  });
  assert.equal(skillMatchesWorkspaceSegment(downloaded, "downloaded"), true);
  assert.equal(skillMatchesWorkspaceSegment(downloaded, "updates"), true);
});

void test("separates forked Personal Space rows from downloaded rows", () => {
  const forked = skill({
    category: "custom",
    space: "personal",
    source_kind: "fork",
    viewer_relation: "forked",
    owner_display_name: "Original Publisher",
    skill_definition_id: 902,
    skill_install_id: 903,
    current_platform_version: 1,
  });

  assert.deepEqual(getSkillWorkspaceCardState(forked), {
    role: "forked",
    primaryAction: "publish",
    segments: ["all", "authored", "forks"],
  });
  assert.equal(skillMatchesWorkspaceSegment(forked, "authored"), true);
  assert.equal(skillMatchesWorkspaceSegment(forked, "forks"), true);
  assert.equal(skillMatchesWorkspaceSegment(forked, "downloaded"), false);
});

void test("keeps same-name Community cards distinguishable without user-facing IDs", () => {
  const alice = skill({
    name: "same-skill",
    space: "community",
    source_kind: "community",
    viewer_relation: "community_available",
    owner_display_name: "Alice",
    skill_definition_id: 1000,
  });
  const bob = skill({
    name: "same-skill",
    space: "community",
    source_kind: "community",
    viewer_relation: "community_available",
    owner_display_name: "Bob",
    skill_definition_id: 1001,
  });

  assert.notEqual(getSkillIdentityKey(alice), getSkillIdentityKey(bob));
  assert.equal(alice.owner_display_name, "Alice");
  assert.equal(bob.owner_display_name, "Bob");
  assert.equal(getSkillIdentityKey(alice).startsWith("definition:"), true);
  assert.equal(getSkillIdentityKey(bob).startsWith("definition:"), true);
});

void test("filters Community Space by first-class Skill name and author fields", () => {
  const official = skill({
    name: "deep-research",
    space: "community",
    source_kind: "official",
    viewer_relation: "official_available",
    owner_display_name: "official",
    skill_definition_id: 1100,
  });
  const community = skill({
    name: "deck-builder",
    space: "community",
    source_kind: "community",
    viewer_relation: "community_available",
    owner_display_name: "Avery Chen",
    skill_definition_id: 1101,
  });
  const downloaded = skill({
    name: "market-scan",
    space: "community",
    source_kind: "community",
    viewer_relation: "downloaded",
    owner_display_name: "Mina Park",
    skill_definition_id: 1102,
    skill_install_id: 2102,
  });
  const updateAvailable = skill({
    name: "analysis-runner",
    space: "community",
    source_kind: "community",
    viewer_relation: "update_available",
    owner_display_name: "Update Publisher",
    skill_definition_id: 1103,
    skill_install_id: 2103,
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
    skill_definition_id: 1104,
  });
  const sameNameBob = skill({
    name: "duplicate-skill",
    space: "community",
    source_kind: "community",
    viewer_relation: "community_available",
    owner_display_name: "Bob",
    skill_definition_id: 1105,
  });
  const personalDownloaded = skill({
    name: "deck-builder",
    category: "custom",
    space: "personal",
    source_kind: "community",
    viewer_relation: "downloaded",
    owner_display_name: "Avery Chen",
    skill_definition_id: 1101,
    skill_install_id: 2101,
  });
  const rows = [
    official,
    community,
    downloaded,
    updateAvailable,
    sameNameAlice,
    sameNameBob,
    personalDownloaded,
  ];

  assert.deepEqual(
    rows.filter((row) => skillMatchesCommunitySearch(row, "official")),
    [official],
  );
  assert.deepEqual(
    rows.filter((row) => skillMatchesCommunitySearch(row, "avery")),
    [community],
  );
  assert.deepEqual(
    rows.filter((row) => skillMatchesCommunitySearch(row, "market")),
    [downloaded],
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
    [
      community,
      downloaded,
      updateAvailable,
      sameNameAlice,
      sameNameBob,
    ],
  );
  assert.deepEqual(
    [
      official,
      community,
      downloaded,
      updateAvailable,
      sameNameAlice,
      sameNameBob,
    ].map((row) => ({
      key: getSkillIdentityKey(row),
      state: getSkillWorkspaceCardState(row),
    })),
    [
      {
        key: "definition:1100",
        state: {
          role: "official-community",
          primaryAction: "add-to-personal",
          segments: ["all"],
        },
      },
      {
        key: "definition:1101",
        state: {
          role: "community",
          primaryAction: "add-to-personal",
          segments: ["all"],
        },
      },
      {
        key: "definition:1102",
        state: {
          role: "community",
          primaryAction: "view-personal",
          segments: ["all", "downloaded"],
        },
      },
      {
        key: "definition:1103",
        state: {
          role: "community",
          primaryAction: "view-update",
          segments: ["all", "downloaded", "updates"],
        },
      },
      {
        key: "definition:1104",
        state: {
          role: "community",
          primaryAction: "add-to-personal",
          segments: ["all"],
        },
      },
      {
        key: "definition:1105",
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

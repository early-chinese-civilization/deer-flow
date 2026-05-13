import assert from "node:assert/strict";
import test from "node:test";

const { enUS } = await import(
  new URL("../i18n/locales/en-US.ts", import.meta.url).href
);
const { zhCN } = await import(
  new URL("../i18n/locales/zh-CN.ts", import.meta.url).href
);

function collectSkillsCopy(skillsCopy: typeof enUS.settings.skills): string[] {
  return [
    skillsCopy.title,
    skillsCopy.description,
    skillsCopy.createSkill,
    skillsCopy.emptyTitle,
    skillsCopy.emptyDescription,
    skillsCopy.emptyButton,
    skillsCopy.uploadSkill,
    skillsCopy.uploadPending,
    skillsCopy.uploadSuccess,
    skillsCopy.uploadError,
    skillsCopy.publishSkill,
    skillsCopy.installSkill,
    skillsCopy.installPending,
    skillsCopy.installSuccess("demo-skill"),
    skillsCopy.installError,
    skillsCopy.publishSuccess("demo-skill"),
    skillsCopy.publishPending,
    skillsCopy.viewUpdate,
    skillsCopy.updateSuccess("demo-skill"),
    skillsCopy.updateError,
    skillsCopy.updatePending,
    skillsCopy.publishedBy("Demo Publisher"),
    skillsCopy.skillHubTab,
    skillsCopy.mySkillsTab,
    skillsCopy.systemSpaceTab,
    skillsCopy.communitySpaceTab,
    skillsCopy.personalSpaceTab,
    skillsCopy.allSegment,
    skillsCopy.systemSegment,
    skillsCopy.installedSegment,
    skillsCopy.authoredSegment,
    skillsCopy.publishedSegment,
    skillsCopy.updatesSegment,
    skillsCopy.forksSegment,
    skillsCopy.platformVersion(1),
    skillsCopy.skillHubVersion(2),
    skillsCopy.currentVersion(1),
    skillsCopy.currentAndUpdateVersions(1, 2),
    skillsCopy.noPlatformVersion,
    skillsCopy.installed,
    skillsCopy.notInstalled,
    skillsCopy.updateAvailable,
    skillsCopy.availableInCommunity,
    skillsCopy.installedToPersonal,
    skillsCopy.published,
    skillsCopy.unpublished,
    skillsCopy.unpublishedChanges,
    skillsCopy.mySkill,
    skillsCopy.systemDirectUse,
    skillsCopy.publishedByYou,
    skillsCopy.officialSource,
    skillsCopy.communitySource("Demo Publisher"),
    skillsCopy.installedFromSource("Demo Publisher"),
    skillsCopy.installedSource,
    skillsCopy.createdSource,
    skillsCopy.addToPersonalSpace,
    skillsCopy.viewInPersonalSpace,
    skillsCopy.publishUpdate,
    skillsCopy.publishDialogTitle,
    skillsCopy.publishDialogDescription,
    skillsCopy.publishDescriptionLabel,
    skillsCopy.releaseNotesLabel,
    skillsCopy.releaseNotesPlaceholder,
    skillsCopy.releaseNotesHelp,
    skillsCopy.publishAsLatestNotice,
    skillsCopy.confirmPublish,
    skillsCopy.updateDialogTitle,
    skillsCopy.updateDialogDescription,
    skillsCopy.updatePreviewLoading,
    skillsCopy.currentVersionLabel,
    skillsCopy.availableVersionLabel,
    skillsCopy.sourceLabel,
    skillsCopy.publisherLabel,
    skillsCopy.publishedAtLabel,
    skillsCopy.unknownPublisher,
    skillsCopy.affectedAgentsLabel,
    skillsCopy.noAffectedAgents,
    skillsCopy.noReleaseNotes,
    skillsCopy.confirmUpdate,
    skillsCopy.deleteBlocked("demo-agent"),
    skillsCopy.conflictConfirm("demo-skill"),
    skillsCopy.noMySkills,
    skillsCopy.noMySkillsDescription,
    skillsCopy.noAuthoredSkills,
    skillsCopy.noAuthoredSkillsDescription,
    skillsCopy.noInstalledSkills,
    skillsCopy.noInstalledSkillsDescription,
    skillsCopy.noSkillUpdates,
    skillsCopy.noSkillUpdatesDescription,
    skillsCopy.noSkillHubSkills,
    skillsCopy.noSkillHubSkillsDescription,
    skillsCopy.noSystemSkills,
    skillsCopy.noSystemSkillsDescription,
    skillsCopy.noCommunitySearchResults,
    skillsCopy.noCommunitySearchResultsDescription,
    skillsCopy.browseCommunitySkills,
    skillsCopy.clearSearch,
  ];
}

function collectAgentSkillCopy(agentsCopy: typeof enUS.agents): string[] {
  return [
    agentsCopy.createSkillsTitle,
    agentsCopy.createSkillsHint,
    agentsCopy.createSkillsEmpty,
    agentsCopy.createSkillsLoading,
    agentsCopy.skillSourceMySkills,
    agentsCopy.skillSourceSkillHub,
    agentsCopy.skillSourceOfficial,
    agentsCopy.skillSourceUnknown,
    agentsCopy.skillVersionUnavailable,
    agentsCopy.skillUpdateAvailable,
    agentsCopy.skillMetadataUnavailable,
    agentsCopy.enabledSkillsLabel,
    agentsCopy.noBoundSkills,
  ];
}

void test("Skills locale copy uses SkillHub and install terminology", () => {
  assert.equal(enUS.settings.skills.systemSpaceTab, "System Skills");
  assert.equal(enUS.settings.skills.communitySpaceTab, "Community Skills");
  assert.equal(enUS.settings.skills.personalSpaceTab, "My Skills");
  assert.equal(enUS.settings.skills.addToPersonalSpace, "Install");
  assert.equal(enUS.settings.skills.installedSegment, "Installed");
  assert.equal(enUS.settings.skills.installedToPersonal, "Installed");
  assert.equal(zhCN.settings.skills.systemSpaceTab, "系统 Skills");
  assert.equal(zhCN.settings.skills.communitySpaceTab, "社区 Skills");
  assert.equal(zhCN.settings.skills.personalSpaceTab, "我的 Skills");
  assert.equal(zhCN.settings.skills.addToPersonalSpace, "安装");
  assert.equal(zhCN.settings.skills.installedSegment, "已安装");
  assert.equal(zhCN.settings.skills.installedToPersonal, "已安装");
});

void test("Skills visible IA avoids Space and Fork labels", () => {
  const englishIaCopy = [
    enUS.settings.skills.systemSpaceTab,
    enUS.settings.skills.communitySpaceTab,
    enUS.settings.skills.personalSpaceTab,
    enUS.settings.skills.allSegment,
    enUS.settings.skills.systemSegment,
    enUS.settings.skills.installedSegment,
    enUS.settings.skills.authoredSegment,
    enUS.settings.skills.updatesSegment,
    enUS.settings.skills.forksSegment,
    enUS.settings.skills.availableInCommunity,
    enUS.settings.skills.installedToPersonal,
    enUS.settings.skills.officialSource,
    enUS.settings.skills.systemDirectUse,
    enUS.settings.skills.installedSource,
    enUS.settings.skills.createdSource,
    enUS.settings.skills.viewInPersonalSpace,
  ].join(" ");
  const chineseIaCopy = [
    zhCN.settings.skills.systemSpaceTab,
    zhCN.settings.skills.communitySpaceTab,
    zhCN.settings.skills.personalSpaceTab,
    zhCN.settings.skills.allSegment,
    zhCN.settings.skills.systemSegment,
    zhCN.settings.skills.installedSegment,
    zhCN.settings.skills.authoredSegment,
    zhCN.settings.skills.updatesSegment,
    zhCN.settings.skills.forksSegment,
    zhCN.settings.skills.availableInCommunity,
    zhCN.settings.skills.installedToPersonal,
    zhCN.settings.skills.officialSource,
    zhCN.settings.skills.systemDirectUse,
    zhCN.settings.skills.installedSource,
    zhCN.settings.skills.createdSource,
    zhCN.settings.skills.viewInPersonalSpace,
  ].join(" ");

  assert.doesNotMatch(englishIaCopy, /\bspace\b|\bforks?\b/i);
  assert.doesNotMatch(chineseIaCopy, /空间|Forks?|forks?/i);
});

void test("SkillHub install copy does not expose download terminology", () => {
  assert.doesNotMatch(
    [
      enUS.settings.skills.addToPersonalSpace,
      enUS.settings.skills.installSkill,
      enUS.settings.skills.installPending,
      enUS.settings.skills.installSuccess("demo-skill"),
      enUS.settings.skills.installError,
    ].join(" "),
    /download/i,
  );
  assert.doesNotMatch(
    [
      zhCN.settings.skills.addToPersonalSpace,
      zhCN.settings.skills.installSkill,
      zhCN.settings.skills.installPending,
      zhCN.settings.skills.installSuccess("demo-skill"),
      zhCN.settings.skills.installError,
    ].join(" "),
    /下载/,
  );
});

void test("publish copy avoids release/package internals in user-facing text", () => {
  const englishPublishCopy = [
    enUS.settings.skills.releaseNotesHelp,
    enUS.settings.skills.publishAsLatestNotice,
    enUS.settings.skills.confirmPublish,
  ].join(" ");

  assert.doesNotMatch(englishPublishCopy, /SKILL\.md|public latest|download/i);
  assert.match(englishPublishCopy, /SkillHub/);
  assert.match(englishPublishCopy, /platform version/);
});

void test("update confirmation copy avoids public latest and package internals", () => {
  const englishUpdateCopy = [
    enUS.settings.skills.updateDialogTitle,
    enUS.settings.skills.updateDialogDescription,
    enUS.settings.skills.currentVersionLabel,
    enUS.settings.skills.availableVersionLabel,
    enUS.settings.skills.affectedAgentsLabel,
    enUS.settings.skills.publishedAtLabel,
    enUS.settings.skills.confirmUpdate,
  ].join(" ");

  assert.doesNotMatch(
    englishUpdateCopy,
    /public latest|package version|release version|artifact/i,
  );
  assert.match(englishUpdateCopy, /version/i);
});

void test("Skills workspace copy avoids forbidden internal terms", () => {
  const forbiddenTerms =
    /public latest|custom|package version|artifact|Runtime Manifest|skill_definition_id|skill_install_id|skill_installation_id|source namespace/i;

  assert.doesNotMatch(
    collectSkillsCopy(enUS.settings.skills).join(" "),
    forbiddenTerms,
  );
  assert.doesNotMatch(
    collectSkillsCopy(zhCN.settings.skills).join(" "),
    forbiddenTerms,
  );
});

void test("Agent and chat Skill metadata copy avoids forbidden internal terms", () => {
  const forbiddenTerms =
    /package version|artifact|Runtime Manifest|skill_definition_id|skill_install_id|skill_installation_id|source namespace/i;

  assert.doesNotMatch(
    collectAgentSkillCopy(enUS.agents).join(" "),
    forbiddenTerms,
  );
  assert.doesNotMatch(
    collectAgentSkillCopy(zhCN.agents).join(" "),
    forbiddenTerms,
  );
});

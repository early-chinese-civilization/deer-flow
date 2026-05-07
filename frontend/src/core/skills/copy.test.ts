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
    skillsCopy.communitySpaceTab,
    skillsCopy.personalSpaceTab,
    skillsCopy.allSegment,
    skillsCopy.downloadedSegment,
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
    skillsCopy.downloadedToPersonal,
    skillsCopy.published,
    skillsCopy.unpublished,
    skillsCopy.unpublishedChanges,
    skillsCopy.mySkill,
    skillsCopy.publishedByYou,
    skillsCopy.forkedSkill,
    skillsCopy.officialSource,
    skillsCopy.communitySource("Demo Publisher"),
    skillsCopy.downloadedSource("Demo Publisher"),
    skillsCopy.forkedSource("Demo Publisher"),
    skillsCopy.installedSource,
    skillsCopy.createdSource,
    skillsCopy.addToPersonalSpace,
    skillsCopy.viewInPersonalSpace,
    skillsCopy.managePublished,
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
    skillsCopy.noSkillHubSkills,
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
  assert.equal(enUS.settings.skills.communitySpaceTab, "Community Space");
  assert.equal(enUS.settings.skills.personalSpaceTab, "Personal Space");
  assert.equal(
    enUS.settings.skills.addToPersonalSpace,
    "Add to Personal Space",
  );
  assert.equal(zhCN.settings.skills.communitySpaceTab, "社区空间");
  assert.equal(zhCN.settings.skills.personalSpaceTab, "我的空间");
  assert.equal(zhCN.settings.skills.addToPersonalSpace, "添加到我的空间");
});

void test("Skills locale copy does not expose download terminology", () => {
  assert.doesNotMatch(
    collectSkillsCopy(enUS.settings.skills).join(" "),
    /download/i,
  );
  assert.doesNotMatch(
    collectSkillsCopy(zhCN.settings.skills).join(" "),
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
    /public latest|custom|package version|artifact|Runtime Manifest|skill_definition_id|skill_install_id|source namespace/i;

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
    /package version|artifact|Runtime Manifest|skill_definition_id|skill_install_id|source namespace/i;

  assert.doesNotMatch(
    collectAgentSkillCopy(enUS.agents).join(" "),
    forbiddenTerms,
  );
  assert.doesNotMatch(
    collectAgentSkillCopy(zhCN.agents).join(" "),
    forbiddenTerms,
  );
});

import assert from "node:assert/strict";
import test from "node:test";

import type { SkillInstallUpdatePreview } from "./api";

const { getSkillInstallUpdateDialogState } = await import(
  new URL("./update-preview.ts", import.meta.url).href
);

function preview(
  overrides: Partial<SkillInstallUpdatePreview>,
): SkillInstallUpdatePreview {
  return {
    skill_name: "demo-skill",
    skill_installation_id: 301,
    skill_id: "12345678-1234-5678-1234-567812345678",
    version_number: 2,
    current_platform_version: 1,
    target_platform_version: 2,
    update_available: true,
    status: "available",
    message: "Version 2 is available.",
    source: "SkillHub",
    affected_agents: [{ id: 10, name: "demo-agent" }],
    ...overrides,
  };
}

void test("update preview state enables confirm only for available selected version", () => {
  const state = getSkillInstallUpdateDialogState(preview({}), {
    isPreviewLoading: false,
    isConfirming: false,
  });

  assert.equal(state.canConfirm, true);
  assert.equal(state.confirmDisabled, false);
  assert.equal(state.cancelDisabled, false);
});

void test("cancel stays enabled while preview is read-only loading", () => {
  const state = getSkillInstallUpdateDialogState(null, {
    isPreviewLoading: true,
    isConfirming: false,
  });

  assert.equal(state.canConfirm, false);
  assert.equal(state.confirmDisabled, true);
  assert.equal(state.cancelDisabled, false);
});

void test("confirm is disabled for unavailable previews and during confirmation", () => {
  assert.equal(
    getSkillInstallUpdateDialogState(preview({ status: "unavailable" }), {
      isPreviewLoading: false,
      isConfirming: false,
    }).confirmDisabled,
    true,
  );

  const confirming = getSkillInstallUpdateDialogState(preview({}), {
    isPreviewLoading: false,
    isConfirming: true,
  });

  assert.equal(confirming.confirmDisabled, true);
  assert.equal(confirming.cancelDisabled, true);
});

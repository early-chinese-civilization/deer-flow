import assert from "node:assert/strict";
import test from "node:test";

const { GET } = await import(new URL("./route.ts", import.meta.url).href);

type MockSkill = {
  name: string;
  description?: string | null;
  release_notes?: string | null;
  owner_display_name?: string | null;
  skill_definition_id?: number | null;
  skill_install_id?: number | null;
  current_platform_version?: number | null;
  latest_platform_version?: number | null;
  update_available?: boolean | null;
  space?: string | null;
  source_kind?: string | null;
  viewer_relation?: string | null;
};

async function getMockSkills(): Promise<MockSkill[]> {
  const response = GET();
  const body = (await response.json()) as { skills: MockSkill[] };
  return body.skills;
}

void test("mock Skills payload covers Community and Personal Space states", async () => {
  const skills = await getMockSkills();

  assert.ok(
    skills.some(
      (skill) =>
        skill.space === "community" &&
        skill.source_kind === "community" &&
        skill.viewer_relation === "community_available" &&
        skill.owner_display_name === "Avery Chen",
    ),
  );
  assert.ok(
    skills.some(
      (skill) =>
        skill.space === "community" &&
        skill.source_kind === "official" &&
        skill.viewer_relation === "official_available",
    ),
  );
  assert.ok(
    skills.some(
      (skill) =>
        skill.space === "community" &&
        skill.viewer_relation === "authored_published",
    ),
  );
  assert.ok(
    skills.some(
      (skill) =>
        skill.space === "personal" &&
        skill.viewer_relation === "downloaded" &&
        skill.skill_install_id != null &&
        skill.current_platform_version === 2,
    ),
  );
  assert.ok(
    skills.some(
      (skill) =>
        skill.space === "personal" &&
        skill.viewer_relation === "update_available",
    ),
  );
  assert.ok(
    skills.some(
      (skill) =>
        skill.space === "personal" && skill.viewer_relation === "authored",
    ),
  );
  assert.equal(
    new Set(
      skills
        .filter((skill) => skill.name === "same-name-helper")
        .map((skill) => skill.owner_display_name),
    ).size,
    2,
  );
});

void test("mock Skills payload covers version, publisher, downloader, and fork rows", async () => {
  const skills = await getMockSkills();

  assert.ok(
    skills.some(
      (skill) =>
        skill.space === "community" &&
        skill.viewer_relation === "authored_published" &&
        skill.owner_display_name === "You",
    ),
  );
  assert.ok(
    skills.some(
      (skill) =>
        skill.space === "personal" &&
        skill.viewer_relation === "downloaded" &&
        skill.owner_display_name === "Mina Park" &&
        skill.skill_definition_id === 102,
    ),
  );
  assert.ok(
    skills.some(
      (skill) =>
        skill.space === "personal" &&
        skill.viewer_relation === "update_available" &&
        skill.current_platform_version === 1 &&
        skill.latest_platform_version === 2 &&
        skill.update_available === true,
    ),
  );
  assert.ok(
    skills.some(
      (skill) =>
        skill.space === "personal" &&
        skill.source_kind === "fork" &&
        skill.viewer_relation === "forked",
    ),
  );
});

void test("mock Skills user-facing text avoids forbidden internal terms", async () => {
  const skills = await getMockSkills();
  const userFacingText = skills
    .flatMap((skill) => [
      skill.name,
      skill.description,
      skill.release_notes,
      skill.owner_display_name,
    ])
    .filter(Boolean)
    .join(" ");

  assert.doesNotMatch(
    userFacingText,
    /public latest|custom|package version|artifact|Runtime Manifest|skill_definition_id|skill_install_id|source namespace/i,
  );
});

import assert from "node:assert/strict";
import test from "node:test";

const { GET } = await import(new URL("./route.ts", import.meta.url).href);

type MockSkill = {
  skill_id?: string | null;
  version_number?: number | null;
  name: string;
  description?: string | null;
  release_notes?: string | null;
  owner_display_name?: string | null;
  skill_installation_id?: number | null;
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

void test("mock Skills payload covers System, Community, and Personal states", async () => {
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
        skill.space === "system" &&
        skill.source_kind === "official" &&
        skill.viewer_relation === "system_available",
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
        skill.viewer_relation === "installed" &&
        skill.skill_installation_id != null &&
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

void test("mock Skills payload covers terminal identity, publisher, installer, and update rows", async () => {
  const skills = await getMockSkills();

  assert.ok(
    skills.every(
      (skill) =>
        typeof skill.skill_id === "string" &&
        typeof skill.version_number === "number",
    ),
  );
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
        skill.viewer_relation === "installed" &&
        skill.owner_display_name === "Mina Park" &&
        skill.skill_id === "00000000-0000-0000-0000-000000000102",
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
  assert.equal(
    skills.some((skill) => skill.source_kind === "fork"),
    false,
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
    /public latest|package version|artifact|Runtime Manifest|source namespace/i,
  );
});

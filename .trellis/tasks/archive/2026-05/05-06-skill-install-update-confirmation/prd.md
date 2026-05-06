# Skill install update confirmation

## Goal

Implement the explicit update confirmation flow for installed Skills so publishing a new version never changes an Agent's runtime behavior until the user confirms the install update.

## Requirements

* Compute update availability from `SkillInstall.current_version_id` versus latest published `SkillVersion`.
* Provide an update preview that includes:
  * current installed platform version
  * available platform version
  * release notes or publish metadata when available
  * publisher/source
  * affected Agents bound to the install
* Update only after explicit user confirmation.
* The update action must change `SkillInstall.current_version_id`; it must not rewrite old artifacts or mutate Agent binding rows.
* A run already started with a Manifest must keep using that Manifest. The next run after update may resolve the new version.
* If the install/version/artifact is missing or blocked, show a clear unavailable/error state and do not fallback.

## Acceptance Criteria

* [ ] User can see that an installed Skill has an update.
* [ ] User can inspect current version, target version, release notes, and affected Agents before confirming.
* [ ] Cancelling leaves `SkillInstall.current_version_id` unchanged.
* [ ] Confirming changes `SkillInstall.current_version_id` to the selected version.
* [ ] Agent runtime remains v1 before confirmation and becomes v2 only on the next run after confirmation.
* [ ] Backend tests cover affected-Agent lookup and update behavior.
* [ ] Frontend tests cover preview/cancel/confirm states.

## Definition of Done

* Backend and frontend relevant tests pass.
* API contracts are typed in frontend `src/core/skills`.
* Runtime Manifest tests still prove no auto-drift.
* User-facing copy avoids public latest/package version language.

## Out of Scope

* Rollback to arbitrary historical versions.
* Side-by-side diff of artifact file contents unless a simple summary already exists.
* Run-level readonly bundle hardening.
* Marketplace moderation/governance.

## Technical Approach

Prefer a small backend contract for "update preview" and "confirm update". The preview should be read-only and should not modify install state. The confirm endpoint should accept a specific `skill_version_id` or resolve the latest published version consistently, then update `SkillInstall.current_version_id`.

Runtime relationship must remain:

```text
Publish v2 -> SkillRelease latest changes
Install current_version_id remains v1
Confirm update -> current_version_id becomes v2
Next Runtime Manifest -> v2
```

## Technical Notes

Read before implementing:
* `docs-qy/skills-design/plan/12-user-flow-max-test-implementation-plan.md`
* `docs-qy/skills-design/design/03-boundary-rules.md`
* `docs-qy/skills-design/user-test/02-skill-version-must-pass-user-test-cases.md`
* `.trellis/spec/backend/database-guidelines.md`
* `.trellis/spec/backend/error-handling.md`
* `.trellis/spec/frontend/component-guidelines.md`
* `.trellis/spec/frontend/type-safety.md`
* `.trellis/spec/guides/cross-layer-thinking-guide.md`

